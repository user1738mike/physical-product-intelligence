"""Tenant-serialized policy, durable admission and append-only usage. No payment/provider I/O."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from audit.services import record
from organizations.models import Organization
from organizations.services import ADMIN, OWNER, authorize

from .models import (
    FEATURES,
    METERS,
    Account,
    Assignment,
    AssignmentEvent,
    OperatorEvent,
    Plan,
    Reservation,
    ReservationEvent,
    Usage,
)

PILOT = dict(
    name="Manual pilot",
    **{key: True for key in FEATURES},
    **{key + "_limit": None for key in METERS},
)
DEFINITIONS = {
    "active_products": "Current active product capacity; archival releases capacity.",
    "assessments": (
        "One unit per successfully committed assessment, including indeterminate results."
    ),
    "extractions": (
        "One unit per completed candidate-generation job (deterministic or AI), "
        "including empty or review-required output; candidate count and later review "
        "do not add units."
    ),
}


class Restricted(APIException):
    status_code = 403

    def __init__(self, code, message, **details):
        super().__init__({"code": code, "detail": message, **details})


def month(at=None):
    at = (at or timezone.now()).astimezone(UTC)
    start = datetime(at.year, at.month, 1, tzinfo=UTC)
    end = datetime(at.year + (at.month == 12), at.month % 12 + 1, 1, tzinfo=UTC)
    return start, end


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def lock(org):
    return Organization.objects.select_for_update().get(pk=org.pk)


def assignment_event(item, actor, action, reason):
    AssignmentEvent.objects.create(
        assignment=item,
        actor=actor,
        action=action,
        reason=reason,
        state={
            "status": item.status,
            "starts_at": item.starts_at.isoformat(),
            "ends_at": item.ends_at.isoformat() if item.ends_at else None,
            "plan_id": str(item.plan_id),
        },
    )
    record(
        "commercial." + action,
        actor=actor,
        organization=item.organization,
        target_type="assignment",
        target_id=item.pk,
    )


@transaction.atomic
def enroll(org, actor=None):
    lock(org)
    if Account.objects.filter(organization=org).exists():
        return
    plan, _ = Plan.objects.get_or_create(code="manual-pilot", version=1, defaults=PILOT)
    if any(getattr(plan, key) != value for key, value in PILOT.items()):
        raise Restricted("policy_unavailable", "Organization access policy is unavailable.")
    now = timezone.now()
    Account.objects.create(organization=org, metering_started_at=now)
    assignment = Assignment.objects.create(
        organization=org,
        plan=plan,
        starts_at=now,
        actor=actor,
        reason="Initial manual pilot enrollment",
    )
    assignment_event(assignment, actor, "enrolled", assignment.reason)


def current(org, at=None):
    now = at or timezone.now()
    return (
        Assignment.objects.select_related("plan")
        .filter(organization=org, starts_at__lte=now)
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .first()
    )


def require(org, feature):
    if feature not in FEATURES:
        raise ValueError("Unknown entitlement")
    lock(org)
    item = current(org)
    if not Account.objects.filter(organization=org).exists() or item is None:
        raise Restricted(
            "access_expired",
            "New work is unavailable because organization access has ended or is not assigned.",
        )
    if item.status != "active":
        raise Restricted(
            "access_suspended", "New work is unavailable while organization access is suspended."
        )
    if not getattr(item.plan, feature):
        raise Restricted(
            "feature_unavailable",
            "Your current plan does not include this action.",
            feature=feature,
        )
    return item


def integration_policy(org, *, new_work=False, webhooks=False):
    """New versioned policy extensions never mutate historical plan definitions."""
    from integrations.models import PlanPolicy

    lock(org)
    item = current(org)
    if item is None and not new_work:
        item = (
            Assignment.objects.filter(organization=org, ends_at__lte=timezone.now())
            .order_by("-ends_at")
            .first()
        )
    policy = PlanPolicy.objects.filter(plan=item.plan).first() if item else None
    if (
        not item
        or item.status != "active"
        or not policy
        or not getattr(policy, "webhooks_enabled" if webhooks else "api_enabled")
    ):
        raise Restricted(
            "feature_unavailable", "Your current plan does not include this integration action."
        )
    return policy


def totals(org, meter, start):
    used = (
        Usage.objects.filter(organization=org, meter=meter, period_start=start).aggregate(
            n=Sum("amount")
        )["n"]
        or 0
    )
    reserved = Reservation.objects.filter(
        organization=org, meter=meter, period_start=start, state="reserved"
    ).count()
    if used < 0:
        raise Restricted(
            "policy_inconsistent", "Usage needs an operator review before new work can begin."
        )
    return used, reserved


def decision(item, reason):
    ReservationEvent.objects.create(
        reservation=item,
        assignment=item.assignment,
        state=item.state,
        fence=item.fence,
        reason=reason,
    )


def capacity(org):
    from products.models import Product

    item = require(org, "catalog_write")
    limit = item.plan.active_products_limit
    used = Product.objects.filter(organization=org, is_active=True).count()
    if limit is not None and used >= limit:
        raise Restricted(
            "capacity_exhausted",
            f"Active product limit reached ({used} of {limit}). "
            "Archive a product before adding another.",
            meter="active_products",
            limit=limit,
            used=used,
        )


@transaction.atomic
def reserve(org, meter, operation, digest, *, fence="", at=None):
    if meter not in {"assessments", "extractions"}:
        raise ValueError("Unknown event meter")
    lock(org)
    old = Reservation.objects.filter(organization=org, meter=meter, operation=operation).first()
    if old and old.fingerprint != digest:
        raise Restricted(
            "operation_conflict",
            "This operation identifier was already used with different inputs.",
        )
    if old and old.state in {"reserved", "finalized"}:
        return old
    item = require(org, "assessments" if meter == "assessments" else "evidence_import")
    if old and old.state == "released":
        # A retry retains its originally admitted month; it must compete for capacity again.
        start, end = old.period_start, old.period_end
    else:
        start, end = month(at)
    used, reserved = totals(org, meter, start)
    limit = getattr(item.plan, meter + "_limit")
    if limit is not None and used + reserved >= limit:
        raise Restricted(
            "quota_exhausted",
            f"Monthly {meter} allowance reached ({used} completed, "
            f"{reserved} in progress, limit {limit}). Period ends {end.isoformat()}.",
            meter=meter,
            limit=limit,
            used=used,
            reserved=reserved,
            period_end=end.isoformat(),
        )
    if old:
        old.state, old.fence, old.assignment = "reserved", fence, item
        old.save(update_fields=["state", "fence", "assignment"])
        decision(old, "Retry admitted")
        return old
    result = Reservation.objects.create(
        organization=org,
        assignment=item,
        meter=meter,
        operation=operation,
        fingerprint=digest,
        period_start=start,
        period_end=end,
        fence=fence,
    )
    decision(result, "Operation admitted")
    return result


@transaction.atomic
def finalize(org, meter, operation, actor, *, fence=""):
    lock(org)
    item = Reservation.objects.select_for_update().get(
        organization=org, meter=meter, operation=operation
    )
    if item.state == "finalized":
        return
    if item.state != "reserved" or item.fence != fence:
        raise Restricted(
            "reservation_fenced", "This processing attempt is no longer authorized to complete."
        )
    Usage.objects.create(
        organization=org,
        reservation=item,
        assignment=item.assignment,
        operation=item.operation,
        meter=meter,
        period_start=item.period_start,
        period_end=item.period_end,
        amount=1,
        actor=actor,
        reason="Successful business operation",
    )
    item.state = "finalized"
    item.save(update_fields=["state"])
    decision(item, "Successful completion")


@transaction.atomic
def release(org, operation):
    lock(org)
    item = Reservation.objects.filter(
        organization=org, meter="extractions", operation=operation, state="reserved"
    ).first()
    if item:
        item.state, item.fence = "released", ""
        item.save(update_fields=["state", "fence"])
        decision(item, "Failure, cancellation or fenced recovery")


def operator(actor):
    from operations.database import runtime_role_privileged

    if not actor or not actor.is_active or not actor.is_staff or not runtime_role_privileged():
        raise PermissionDenied(
            "Commercial changes require an explicit active operator and migration-owner connection."
        )


@transaction.atomic
def publish(actor, *, code, version, name, policy, reason="Explicit operator publication"):
    operator(actor)
    allowed = set(FEATURES) | {key + "_limit" for key in METERS}
    if (
        set(policy) != allowed
        or any(type(policy[k]) is not bool for k in FEATURES)
        or any(
            policy[k + "_limit"] is not None
            and (
                type(policy[k + "_limit"]) is not int or not 0 <= policy[k + "_limit"] <= 2147483647
            )
            for k in METERS
        )
    ):
        raise ValidationError(
            "Supply exactly the documented boolean features and nonnegative integer/null limits."
        )
    item = Plan(code=code, version=version, name=name, **policy)
    item.full_clean(exclude=[key + "_limit" for key in METERS if policy[key + "_limit"] is None])
    item.save()
    OperatorEvent.objects.create(
        actor=actor, action="plan_published", reason=reason, reference=str(item.pk)
    )
    record("commercial.plan_published", actor=actor, target_type="plan", target_id=item.pk)
    return item


@transaction.atomic
def assign(actor, org, plan, *, reason, starts_at=None, ends_at=None, source="manual_pilot"):
    operator(actor)
    lock(org)
    start = starts_at or timezone.now()
    if (
        not reason.strip()
        or source not in {"manual_pilot", "verified_payment"}
        or start < timezone.now() - timedelta(seconds=5)
        or (ends_at is not None and ends_at <= start)
    ):
        raise ValidationError("A reason and a valid current/future exclusive period are required.")
    overlapping = (
        Assignment.objects.filter(organization=org)
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=start))
        .order_by("starts_at")
    )
    for old in overlapping:
        if old.starts_at >= start:
            raise ValidationError(
                "A scheduled assignment conflicts; expire it explicitly before replacing."
            )
        old.ends_at = start
        old.save(update_fields=["ends_at"])
        assignment_event(old, actor, "replaced", reason)
    item = Assignment.objects.create(
        organization=org,
        plan=plan,
        actor=actor,
        starts_at=start,
        ends_at=ends_at,
        reason=reason,
        source=source,
    )
    assignment_event(item, actor, "assigned", reason)
    return item


@transaction.atomic
def transition(actor, org, assignment_id, *, action, reason, ends_at=None):
    operator(actor)
    lock(org)
    item = Assignment.objects.get(organization=org, pk=assignment_id)
    if not reason.strip():
        raise ValidationError("A reason is required.")
    if action in {"suspend", "resume"}:
        item.status = "suspended" if action == "suspend" else "active"
    elif (
        action == "expire"
        and ends_at
        and ends_at > item.starts_at
        and (item.ends_at is None or ends_at <= item.ends_at)
    ):
        item.ends_at = ends_at
    else:
        raise ValidationError("Use suspend, resume, or expire with a valid shortened period.")
    item.save(update_fields=["status", "ends_at"])
    assignment_event(item, actor, action, reason)
    return item


@transaction.atomic
def adjust(actor, org, usage_id, *, amount, operation, reason):
    operator(actor)
    lock(org)
    original = Usage.objects.get(organization=org, pk=usage_id, adjustment_of__isnull=True)
    old = Usage.objects.filter(organization=org, meter=original.meter, operation=operation).first()
    if old:
        if old.adjustment_of_id != original.pk or old.amount != amount or old.reason != reason:
            raise ValidationError("Adjustment identity conflict.")
        return old
    used, _ = totals(org, original.meter, original.period_start)
    if type(amount) is not int or not amount or used + amount < 0 or not reason.strip():
        raise ValidationError(
            "Use a nonzero integer adjustment with a reason and nonnegative resulting usage."
        )
    item = Usage.objects.create(
        organization=org,
        assignment=original.assignment,
        adjustment_of=original,
        operation=operation,
        meter=original.meter,
        period_start=original.period_start,
        period_end=original.period_end,
        amount=amount,
        actor=actor,
        reason=reason,
    )
    record(
        "commercial.usage_adjusted",
        actor=actor,
        organization=org,
        target_type="usage",
        target_id=item.pk,
    )
    return item


@transaction.atomic
def summary(actor, org_id):
    from products.models import Product

    org, _ = authorize(actor, org_id, roles={OWNER, ADMIN}, allow_suspended=True, lock=True)
    item, now = current(org), timezone.now()
    account = Account.objects.filter(organization=org).first()
    start, end = month(now)
    latest = (
        Assignment.objects.filter(organization=org, starts_at__lte=now)
        .select_related("plan")
        .order_by("-starts_at")
        .first()
    )
    status = "unassigned" if latest is None else "expired" if item is None else item.status
    if not org.is_active:
        status = "suspended"
    plan = (item or latest).plan if item or latest else None
    from integrations.models import PlanPolicy

    integration = PlanPolicy.objects.filter(plan=plan).first() if plan else None
    meters = {}
    for meter in METERS:
        used, reserved = (
            (Product.objects.filter(organization=org, is_active=True).count(), 0)
            if meter == "active_products"
            else totals(org, meter, start)
        )
        limit = getattr(plan, meter + "_limit") if plan else 0
        meters[meter] = {
            "definition": DEFINITIONS[meter],
            "limit": limit,
            "used": used,
            "reserved": reserved,
            "remaining": None if limit is None else max(0, limit - used - reserved),
        }
    return {
        "status": status,
        "plan": {
            "code": plan.code,
            "version": plan.version,
            "name": plan.name,
            "features": {
                **{key: getattr(plan, key) for key in FEATURES},
                "integration_api": bool(integration and integration.api_enabled),
                "outbound_webhooks": bool(integration and integration.webhooks_enabled),
            },
        }
        if plan
        else None,
        "starts_at": (item or latest).starts_at if item or latest else None,
        "ends_at": (item or latest).ends_at if item or latest else None,
        "period_start": start,
        "period_end": end,
        "metering_started_at": account.metering_started_at if account else None,
        "historical_usage_complete": False,
        "meters": meters,
        "history": [
            {
                "id": a.pk,
                "plan_code": a.plan.code,
                "plan_version": a.plan.version,
                "starts_at": a.starts_at,
                "ends_at": a.ends_at,
                "status": a.status,
                "source": a.source,
            }
            for a in Assignment.objects.filter(organization=org)
            .select_related("plan")
            .order_by("-starts_at")[:50]
        ],
    }


@transaction.atomic
def recover(actor, org, *, reason, limit=50):
    """Fence stale original workers by changing job state under the same tenant/job locks."""
    from ingestion.models import ImportJob
    from ingestion.services import save_job

    operator(actor)
    lock(org)
    if not reason.strip() or not 1 <= limit <= 100:
        raise ValidationError("Reason and bounded limit (1..100) required.")
    OperatorEvent.objects.create(actor=actor, organization=org, action="recovery", reason=reason)
    jobs = (
        ImportJob.objects.select_for_update()
        .filter(
            organization=org,
            mode="ai",
            status="processing",
            started_at__lte=timezone.now() - timedelta(seconds=90),
        )
        .order_by("started_at")[:limit]
    )
    count = 0
    for job in jobs:
        job.status, job.completed_at = "failed", timezone.now()
        job.extraction.update(
            lease="", retryable=job.extraction.get("attempts", 3) < 3, stage="failed"
        )
        job.errors = [
            {"code": "abandoned_work", "message": "Processing was interrupted; retry if available."}
        ]
        save_job(job)
        release(org, job.pk)
        record(
            "commercial.reservation_recovered",
            actor=actor,
            organization=org,
            target_type="importjob",
            target_id=job.pk,
        )
        count += 1
    return count


@transaction.atomic
def reconcile(actor, org, *, reason):
    from compatibility.models import Assessment

    operator(actor)
    lock(org)
    if not reason.strip():
        raise ValidationError("A reason is required.")
    account = Account.objects.get(organization=org)
    OperatorEvent.objects.create(
        actor=actor, organization=org, action="reconciliation", reason=reason
    )
    assessment_operations = Usage.objects.filter(
        organization=org, meter="assessments", adjustment_of__isnull=True
    ).values("operation")
    missing = (
        Assessment.objects.filter(organization=org, created_at__gte=account.metering_started_at)
        .exclude(request_id__in=assessment_operations)
        .count()
    )
    finalized = Reservation.objects.filter(organization=org, state="finalized")
    missing_ledger = finalized.exclude(
        pk__in=Usage.objects.filter(organization=org).values("reservation_id")
    ).count()
    record(
        "commercial.usage_reconciled",
        actor=actor,
        organization=org,
        target_type="organization",
        target_id=org.pk,
    )
    return {
        "metering_started_at": account.metering_started_at,
        "historical_usage_complete": False,
        "missing_assessment_events": missing,
        "missing_finalized_events": missing_ledger,
        "reserved": Reservation.objects.filter(organization=org, state="reserved").count(),
        "history_rewritten": False,
    }
