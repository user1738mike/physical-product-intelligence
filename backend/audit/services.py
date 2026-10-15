import logging

from django.db import transaction

from .models import AuditEvent


def record(
    action,
    *,
    actor=None,
    organization=None,
    target_type="",
    target_id="",
    outcome="success",
    metadata=None,
):
    metadata = metadata or {}
    if set(metadata) - {"role", "previous_role"} or any(
        value not in {"owner", "admin", "member"} for value in metadata.values()
    ):
        raise ValueError("Unsupported audit metadata")
    result = AuditEvent.objects.create(
        action=action,
        actor=actor,
        organization=organization,
        target_type=target_type,
        target_id=str(target_id),
        outcome=outcome,
        metadata=metadata,
    )
    transaction.on_commit(
        lambda: logging.getLogger("operations.audit").info(
            "audit_event", extra={"action": action, "outcome": outcome}
        )
    )
    return result
