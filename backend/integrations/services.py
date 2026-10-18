import hashlib
import hmac
import json
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, NotFound, Throttled, ValidationError

from audit.services import record
from commercial import services as commercial
from operations.models import RateBucket
from organizations.services import ADMIN, OWNER, authorize

from . import signing, transport
from .models import SCOPES, Admission, Credential, Delivery, DeliveryAttempt, Destination, Event


def log(actor, org, action, target):
    record(
        "integration." + action,
        actor=actor,
        organization=org,
        target_type="integration",
        target_id=target.pk,
    )


def management(actor, org_id, *, new=False, webhooks=False):
    org, _ = authorize(actor, org_id, roles={OWNER, ADMIN}, allow_suspended=not new, lock=True)
    policy = commercial.integration_policy(org, new_work=True, webhooks=webhooks) if new else None
    return org, policy


@transaction.atomic
def create_credential(actor, org_id, *, name, scopes, expires_at, rotate=None, revoke_old=True):
    org, policy = management(actor, org_id, new=True)
    now = timezone.now()
    if (
        not isinstance(scopes, list)
        or not scopes
        or len(scopes) != len(set(scopes))
        or not set(scopes) <= set(SCOPES)
    ):
        raise ValidationError("Select explicit read-only scopes.")
    if not now + timedelta(minutes=1) <= expires_at <= now + timedelta(days=90):
        raise ValidationError("Expiry must be between one minute and 90 days.")
    old = Credential.objects.filter(organization=org, pk=rotate).first() if rotate else None
    if rotate and (not old or old.revoked_at is not None):
        raise NotFound("Credential not found.")
    if old and revoke_old:
        old.revoked_at = now
        old.save(update_fields=["revoked_at"])
    if (
        Credential.objects.filter(
            organization=org, revoked_at__isnull=True, expires_at__gt=now
        ).count()
        >= policy.credentials_limit
    ):
        raise ValidationError("Active credential allowance reached.")
    item = Credential(
        id=uuid.uuid4(),
        organization=org,
        issuer=actor,
        name=name,
        scopes=scopes,
        expires_at=expires_at,
    )
    token = "ppi_i_" + item.pk.hex + "." + secrets.token_urlsafe(32)
    item.verifier = hashlib.sha256(token.encode()).hexdigest()
    item.full_clean(exclude=["revoked_at", "last_used_at"])
    item.save()
    log(actor, org, "credential_rotated" if old else "credential_created", item)
    return item, token


@transaction.atomic
def revoke(actor, org_id, credential_id):
    org, _ = management(actor, org_id)
    try:
        item = Credential.objects.get(organization=org, pk=credential_id)
    except Credential.DoesNotExist:
        raise NotFound("Credential not found.") from None
    if item.revoked_at is None:
        item.revoked_at = timezone.now()
        item.save(update_fields=["revoked_at"])
        log(actor, org, "credential_revoked", item)
    return item


@transaction.atomic
def authenticate(token):
    try:
        if len(token) != 82 or not token.startswith("ppi_i_") or token[38] != ".":
            raise ValueError()
        ident = uuid.UUID(hex=token[6:38])
        item = Credential.objects.select_related("issuer", "organization").get(pk=ident)
        commercial.lock(item.organization)
        item.refresh_from_db()
        now = timezone.now()
        if (
            item.revoked_at
            or item.expires_at <= now
            or not hmac.compare_digest(item.verifier, hashlib.sha256(token.encode()).hexdigest())
        ):
            raise ValueError()
        org, _ = authorize(item.issuer, item.organization_id, roles={OWNER, ADMIN})
        commercial.integration_policy(org)
        return item
    except (ValueError, Credential.DoesNotExist, NotFound):
        raise AuthenticationFailed("Invalid integration credential.") from None


@transaction.atomic
def admit(credential):
    commercial.lock(credential.organization)
    # Recheck revocation and issuer role after acquiring the shared admission lock.
    current = Credential.objects.get(pk=credential.pk)
    now = timezone.now()
    if current.revoked_at or current.expires_at <= now:
        raise AuthenticationFailed("Invalid integration credential.")
    authorize(credential.issuer, credential.organization_id, roles={OWNER, ADMIN})
    commercial.integration_policy(credential.organization)
    Admission.objects.filter(expires_at__lte=now).delete()
    if (
        Admission.objects.filter(credential__organization=credential.organization).count() >= 4
        or Admission.objects.filter(credential=credential).count() >= 2
    ):
        raise Throttled(wait=20, detail="Integration concurrency limit reached.")
    window = int(now.timestamp()) // 60
    buckets = []
    for label, limit in (
        ("org:" + str(credential.organization_id), settings.INTEGRATION_ORG_RATE),
        ("key:" + str(credential.pk), settings.INTEGRATION_KEY_RATE),
    ):
        bucket, _ = RateBucket.objects.get_or_create(
            key=hashlib.sha256(("integration:" + label).encode()).hexdigest(),
            defaults={"window_start": window, "expires_at": now + timedelta(minutes=2)},
        )
        if bucket.window_start != window:
            bucket.window_start, bucket.count = window, 0
        if bucket.count >= limit:
            raise Throttled(
                wait=60 - int(now.timestamp()) % 60, detail="Integration request limit reached."
            )
        buckets.append(bucket)
    for bucket in buckets:
        bucket.count += 1
        bucket.expires_at = now + timedelta(minutes=2)
        bucket.save()
    if not current.last_used_at or current.last_used_at < now - timedelta(minutes=1):
        current.last_used_at = now
        current.save(update_fields=["last_used_at"])
    return Admission.objects.create(credential=credential, expires_at=now + timedelta(seconds=20))


def available():
    return bool(
        settings.INTEGRATION_OUTBOUND_ENABLED
        and settings.INTEGRATION_ALLOWED_HOSTS
        and settings.INTEGRATION_SIGNING_CURRENT in settings.INTEGRATION_SIGNING_KEYS
    )


@transaction.atomic
def configure_destination(
    actor, org_id, *, url, subscriptions, destination_id=None, enabled=True, expected_revision=None
):
    org, policy = management(actor, org_id, new=enabled, webhooks=True)
    if enabled and not available():
        raise ValidationError("Outbound notifications are not available.")
    if subscriptions != ["assessment.completed"] and subscriptions != []:
        raise ValidationError("Select supported event subscriptions.")
    if enabled:
        transport.url_parts(url)
    item = (
        Destination.objects.filter(organization=org, pk=destination_id).first()
        if destination_id
        else None
    )
    if destination_id and item is None:
        raise NotFound("Destination not found.")
    if item:
        if item.revision != expected_revision:
            raise ValidationError("Destination changed; refresh before editing.")
        if (
            enabled
            and not item.enabled
            and Destination.objects.filter(organization=org, enabled=True).count()
            >= policy.destinations_limit
        ):
            raise ValidationError("Destination allowance reached.")
        Delivery.objects.filter(
            destination=item, state__in=["pending", "claimed", "retryable"]
        ).update(state="paused", lease=None, lease_until=None, diagnostic="destination_changed")
        item.revision += 1
    else:
        if (
            not enabled
            or Destination.objects.filter(organization=org, enabled=True).count()
            >= policy.destinations_limit
        ):
            raise ValidationError("Destination allowance reached.")
        item = Destination(
            organization=org, issuer=actor, root_version=settings.INTEGRATION_SIGNING_CURRENT
        )
    item.url, item.subscriptions, item.enabled = (
        url if enabled else item.url,
        subscriptions,
        enabled,
    )
    item.full_clean(exclude=["previous_key_version", "overlap_until", "subscriptions"])
    item.save()
    log(actor, org, "destination_changed", item)
    # Signing secret only returned on initial creation/explicit rotation, never general reads.
    return item, signing.endpoint_key(item) if not destination_id else None


@transaction.atomic
def rotate_signing(actor, org_id, destination_id, *, immediate=False):
    org, _ = management(actor, org_id, new=True, webhooks=True)
    try:
        item = Destination.objects.get(organization=org, pk=destination_id)
    except Destination.DoesNotExist:
        raise NotFound("Destination not found.") from None
    item.previous_key_version = None if immediate else item.key_version
    item.overlap_until = timezone.now() + timedelta(hours=24)
    item.key_version += 1
    item.save()
    log(actor, org, "signing_rotated", item)
    return item, signing.endpoint_key(item)


def assessment_committed(assessment):
    """Called inside the assessment transaction. No I/O, no additional billable usage."""
    item = Event(id=uuid.uuid4(), organization=assessment.organization, assessment=assessment)
    item.body = json.dumps(
        {
            "schema_version": "1",
            "id": str(item.pk),
            "type": "assessment.completed",
            "occurred_at": assessment.created_at.isoformat(),
            "organization_id": str(assessment.organization_id),
            "data": {
                "assessment_id": str(assessment.pk),
                "overall": assessment.overall,
                "path": f"/api/v1/integration/assessments/{assessment.pk}/",
            },
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    item.save()
    for destination in Destination.objects.filter(
        organization=assessment.organization, enabled=True
    ):
        if item.kind in destination.subscriptions:
            Delivery.objects.create(
                event=item,
                destination=destination,
                revision=destination.revision,
                expires_at=timezone.now() + timedelta(days=3),
            )


def dispatch_allowed(destination):
    if not destination.enabled or not available():
        return False
    try:
        authorize(destination.issuer, destination.organization_id, roles={OWNER, ADMIN})
        commercial.integration_policy(destination.organization, new_work=True, webhooks=True)
        return True
    except Exception as error:
        from rest_framework.exceptions import APIException

        if isinstance(error, APIException):
            return False
        raise


@transaction.atomic
def claim(delivery_id):
    # One global admission lock bounds active outbound connections across all workers.
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(7101001)")
    now = timezone.now()
    if Delivery.objects.filter(state="claimed", lease_until__gt=now).count() >= 4:
        return None
    candidate = (
        Delivery.objects.select_related("destination__organization").filter(pk=delivery_id).first()
    )
    if not candidate:
        return None
    commercial.lock(candidate.destination.organization)
    item = (
        Delivery.objects.select_for_update(skip_locked=True)
        .select_related("destination__organization", "destination__issuer", "event")
        .filter(pk=delivery_id)
        .first()
    )
    if (
        not item
        or item.state not in {"pending", "retryable", "claimed"}
        or item.due_at > now
        or (item.state == "claimed" and item.lease_until > now)
    ):
        return None
    if item.expires_at <= now or item.attempts >= 6:
        item.state, item.diagnostic = "terminal", "attempts_or_age_limit"
    elif item.revision != item.destination.revision or not dispatch_allowed(item.destination):
        item.state, item.diagnostic = "paused", "destination_unavailable"
    elif (
        Delivery.objects.filter(
            destination__organization=item.destination.organization,
            state="claimed",
            lease_until__gt=now,
        ).count()
        >= 2
    ):
        return None
    else:
        item.state, item.lease, item.lease_until = (
            "claimed",
            uuid.uuid4(),
            now + timedelta(seconds=30),
        )
        item.attempts += 1
    item.save()
    return item if item.state == "claimed" else None


@transaction.atomic
def finish(item, status, retry_after, diagnostic):
    commercial.lock(item.destination.organization)
    current = (
        Delivery.objects.select_for_update()
        .select_related("destination__organization", "destination__issuer")
        .get(pk=item.pk)
    )
    if (
        current.state != "claimed"
        or current.lease != item.lease
        or current.lease_until <= timezone.now()
    ):
        return "fenced"
    if current.revision != current.destination.revision or not dispatch_allowed(
        current.destination
    ):
        current.state, diagnostic = "paused", "destination_unavailable"
    elif status is not None and 200 <= status <= 299:
        current.state, diagnostic = "delivered", "acknowledged"
    elif status == 410:
        current.destination.enabled = False
        current.destination.save(update_fields=["enabled"])
        Delivery.objects.filter(
            destination=current.destination, state__in=["pending", "retryable"]
        ).update(state="paused", diagnostic="destination_gone")
        current.state, diagnostic = "paused", "destination_gone"
    elif current.attempts >= 6 or current.expires_at <= timezone.now():
        current.state = "terminal"
    else:
        current.state = "retryable"
        delay = max(
            retry_after or 0, min(3600, 30 * 2 ** (current.attempts - 1)) + secrets.randbelow(16)
        )
        current.due_at = timezone.now() + timedelta(seconds=delay)
    current.status_code, current.diagnostic = status, diagnostic
    current.lease, current.lease_until = None, None
    current.save()
    DeliveryAttempt.objects.create(
        delivery=current,
        lease=item.lease,
        state=current.state,
        diagnostic=diagnostic,
        status_code=status,
    )
    return current.state


def dispatch_one(delivery_id, *, sender=None):
    item = claim(delivery_id)
    if not item:
        return "not_claimed"
    # Recheck immediately before network I/O; edits fence completion and pause old revisions.
    with transaction.atomic():
        fresh = Delivery.objects.select_related(
            "destination__organization", "destination__issuer", "event"
        ).get(pk=item.pk)
        if (
            fresh.lease != item.lease
            or fresh.state != "claimed"
            or fresh.revision != fresh.destination.revision
            or not dispatch_allowed(fresh.destination)
        ):
            return finish(item, None, None, "destination_unavailable")
    try:
        status, retry = (sender or transport.send)(
            fresh.destination.url,
            fresh.event.body.encode(),
            signing.headers(fresh.destination, fresh.event, timezone.now()),
        )
        diagnostic = "redirect_rejected" if 300 <= status < 400 else "http_failure"
    except (transport.TransportFailure, ValidationError):
        status, retry, diagnostic = None, None, "network_or_destination_failure"
    return finish(item, status, retry, diagnostic)


@transaction.atomic
def replay(actor, org_id, delivery_id):
    org, _ = management(actor, org_id, new=True, webhooks=True)
    try:
        item = (
            Delivery.objects.select_for_update(of=("self",))
            .select_related("destination")
            .get(pk=delivery_id, event__organization=org)
        )
    except Delivery.DoesNotExist:
        raise NotFound("Delivery not found.") from None
    if (
        item.state == "claimed"
        or item.revision != item.destination.revision
        or not item.destination.enabled
        or item.replays >= 3
    ):
        raise ValidationError("This delivery cannot be replayed.")
    item.state, item.attempts, item.due_at, item.expires_at = (
        "pending",
        0,
        timezone.now(),
        timezone.now() + timedelta(days=3),
    )
    item.replays += 1
    item.save()
    log(actor, org, "delivery_replayed", item)
    return item
