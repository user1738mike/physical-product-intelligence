"""Explicit unused-source disposal; immutable evidence/history are never erased."""

import hashlib
import os
import re
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage, storages
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from audit.services import record
from organizations.models import Membership, Organization
from organizations.services import OWNER, authorize
from products.services import Conflict

from .models import ImportJob, ImportRow, RetentionPolicy, ReviewRecord, SourceRemoval


def policy_for(org):
    return RetentionPolicy.objects.filter(organization=org).first()


def policy_data(org):
    value = policy_for(org)
    return {
        "version": value.version if value else 0,
        "minimum_days": value.minimum_days if value else None,
        "legal_hold": value.legal_hold if value else True,
    }


def event(item, actor, action, reason):
    ReviewRecord.objects.create(
        job=item.source,
        actor=actor,
        action="retention_" + action,
        reason=reason,
        after={
            "removal_id": str(item.pk),
            "sha256": item.sha256,
            "policy_version": item.policy.version,
        },
    )
    record(
        "retention." + action,
        actor=actor,
        organization=item.source.organization,
        target_type="source_removal",
        target_id=item.pk,
    )


@transaction.atomic
def set_policy(actor, org_id, *, expected_version, minimum_days, legal_hold, reason):
    org, _ = authorize(actor, org_id, roles={OWNER}, lock=True)
    if policy_data(org)["version"] != expected_version:
        raise Conflict("Retention policy changed. Reload before continuing.")
    if (
        legal_hold
        and SourceRemoval.objects.filter(
            source__organization=org, state__in=["claimed", "needs_review"]
        ).exists()
    ):
        raise Conflict(
            "A source removal is in progress or uncertain. "
            "Operator reconciliation is required before confirming a hold."
        )
    value = RetentionPolicy.objects.create(
        organization=org,
        actor=actor,
        version=expected_version + 1,
        minimum_days=minimum_days,
        legal_hold=legal_hold,
        reason=reason,
    )
    record(
        "retention.policy_changed",
        actor=actor,
        organization=org,
        target_type="retention_policy",
        target_id=value.pk,
    )
    return policy_data(org)


def eligible(source, policy):
    if not policy or policy.legal_hold or policy.minimum_days is None:
        raise Conflict("Source removal is disabled or subject to legal hold.")
    if source.mode != "deterministic" or source.status not in {"failed", "cancelled"}:
        raise Conflict("Only unused failed or cancelled original uploads may be removed.")
    if source.created_at > timezone.now() - timedelta(days=policy.minimum_days):
        raise Conflict("This source has not reached the configured minimum retention age.")
    family = ImportJob.objects.filter(Q(pk=source.pk) | Q(source_job=source))
    if family.exclude(status__in=["failed", "cancelled"]).exists():
        raise Conflict("An extraction still uses this source. Finish or cancel it first.")
    if (
        ImportRow.objects.filter(job__in=family)
        .filter(Q(applied=True) | Q(evidence__isnull=False) | Q(candidates__claim__isnull=False))
        .exists()
    ):
        raise Conflict("Applied evidence and its original source must be preserved.")


@transaction.atomic
def request_removal(actor, org_id, job_id, *, expected_version, reason):
    from .services import job_in, version

    authorize(actor, org_id, roles={OWNER}, lock=True)
    source = job_in(actor, org_id, job_id, lock=True)
    old = source.removals.exclude(state="cancelled").first()
    if old:
        return old
    version(source, expected_version)
    policy = policy_for(source.organization)
    eligible(source, policy)
    value = SourceRemoval.objects.create(
        source=source,
        actor=actor,
        policy=policy,
        source_version=source.version,
        sha256=source.sha256,
        storage_key=source.storage_key,
        reason=reason,
    )
    event(value, actor, "requested", reason)
    return value


def check_readable(job):
    root_id = job.source_job_id or job.pk
    if SourceRemoval.objects.filter(
        source_id=root_id, state__in=["claimed", "needs_review", "removed"]
    ).exists():
        raise Conflict(
            "Source file removal is in progress or complete. "
            "Its recorded metadata remains available."
        )


def safe_path(source):
    storage = storages["ingestion"]
    if not isinstance(storage, FileSystemStorage):
        raise ValidationError("Source removal requires the reviewed private filesystem storage.")
    if not re.fullmatch(
        str(source.organization_id) + r"/[a-f0-9]{32}\.(csv|xlsx|pdf|txt)", source.storage_key
    ):
        raise ValidationError("Invalid private source identity.")
    root = Path(storage.location).resolve()
    path = Path(storage.path(source.storage_key))
    if path.parent.is_symlink() or path.is_symlink() or path.resolve() != root / source.storage_key:
        raise ValidationError("Invalid private source path.")
    return path


def verified_file(source):
    path = safe_path(source)
    if not 1 <= source.size <= settings.INGESTION_LIMITS["upload_bytes"]:
        raise ValidationError("Source size is invalid.")
    with path.open("rb") as stream:
        data = stream.read(source.size + 1)
    if len(data) != source.size or hashlib.sha256(data).hexdigest() != source.sha256:
        raise ValidationError("Source integrity check failed; removal requires review.")
    return path


def finish(item, state, actor, reason):
    item.state, item.finished_at = state, timezone.now()
    item.save(update_fields=["state", "finished_at"])
    event(item, actor, state, reason)


def process_one(actor, removal_id):
    from operations.processors import operator

    operator(actor)
    with transaction.atomic(durable=True):
        item = SourceRemoval.objects.select_related("source", "policy").get(pk=removal_id)
        org = Organization.objects.select_for_update().get(pk=item.source.organization_id)
        item.refresh_from_db()
        item.source.refresh_from_db()
        if item.state != "queued":
            return False
        current = policy_for(org)
        active_owner = Membership.objects.filter(
            organization=org, user_id=item.actor_id, user__is_active=True, role=OWNER
        ).exists()
        try:
            if (
                not org.is_active
                or not active_owner
                or current != item.policy
                or item.source.version != item.source_version
                or item.source.sha256 != item.sha256
                or item.source.storage_key != item.storage_key
            ):
                raise Conflict("Removal authorization or source changed.")
            eligible(item.source, current)
        except Conflict:
            finish(
                item, "cancelled", actor, "Removal conditions changed; request again after review."
            )
            return False
        item.state = "claimed"
        item.claimed_at = timezone.now()
        item.save(update_fields=["state", "claimed_at"])
        event(item, actor, "claimed", "Durable intent recorded before private file removal.")
    # The committed claim excludes new extraction/read work. A hold cannot be
    # confirmed while this irreversible step is admitted. No DB transaction
    # pretends it can roll back filesystem removal after a crash.
    try:
        operator(actor)
        path = verified_file(item.source)
        # Verification can block on storage. A recovery/reconciliation may have
        # fenced this claim while it was waiting; never unlink on stale intent.
        # The intent above is already committed. This short lock does NOT make
        # filesystem deletion reversible if the process/DB fails afterward.
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=org.pk)
            item.refresh_from_db()
            if item.state != "claimed":
                return False
            operator(actor)
            os.unlink(path)
    except Exception:
        state, reason = (
            "needs_review",
            "Private source removal outcome requires operator reconciliation.",
        )
    else:
        state, reason = (
            "removed",
            "Verified unused original file removed; metadata/history preserved.",
        )
    with transaction.atomic():
        Organization.objects.select_for_update().get(pk=org.pk)
        item.refresh_from_db()
        if item.state == "claimed":
            finish(item, state, actor, reason)
    return item.state == "removed"


def cycle(actor, *, limit=20):
    from operations.processors import operator

    result = {"removed": 0, "failures": 0}
    operator(actor)
    # A crash cannot cause an automatic second unlink. Surface uncertainty.
    stale = SourceRemoval.objects.filter(
        state="claimed", claimed_at__lt=timezone.now() - timedelta(minutes=5)
    )[:limit]
    for item in stale:
        operator(actor)
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=item.source.organization_id)
            item.refresh_from_db()
            if item.state == "claimed":
                finish(
                    item,
                    "needs_review",
                    actor,
                    "Interrupted removal requires operator reconciliation.",
                )
    for pk in SourceRemoval.objects.filter(state="queued").values_list("pk", flat=True)[:limit]:
        try:
            result["removed"] += process_one(actor, pk)
        except Exception:
            result["failures"] += 1
    return result


@transaction.atomic
def reconcile(actor, removal_id, *, reason):
    """Trusted operator confirms physical presence/absence after quiescing workers."""
    from operations.processors import operator

    operator(actor)
    item = SourceRemoval.objects.select_related("source").get(pk=removal_id)
    Organization.objects.select_for_update().get(pk=item.source.organization_id)
    item.refresh_from_db()
    if item.state != "needs_review":
        raise Conflict("Only an uncertain removal can be reconciled.")
    path = safe_path(item.source)
    if path.exists():
        verified_file(item.source)
        finish(item, "cancelled", actor, reason)
    else:
        finish(item, "removed", actor, reason)
    return item
