"""Recover verified financial records with lookups only; never initiate/resubmit payments."""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from billing import adapter, services
from billing.models import Inbox, PaymentOperation
from operations.processors import operator


def cycle(actor, *, limit=10):
    operator(actor)
    if not 1 <= limit <= 10:
        raise ValueError("Billing cycle limit must be 1..10 per lane")
    result = {"lookups": 0, "events": 0, "unavailable": 0, "failures": 0}
    if not adapter.enabled():
        result["unavailable"] = 1
        return result
    now = timezone.now()
    stale = Q(state="processing", leased_at__lte=now - timedelta(seconds=90))
    # Only the executable isolated adapter is configured today. A concrete
    # provider must supply its own verified mode/identity selection when added.
    operations = list(
        PaymentOperation.objects.filter(
            provider="simulator",
            mode="test",
            next_check_at__lte=now,
            expires_at__gt=now - timedelta(days=3),
        )
        .filter(Q(state__in=["unknown", "ready"]) | stale | Q(state="pending", expires_at__lte=now))
        .order_by("next_check_at", "pk")
        .values_list("pk", flat=True)[:limit]
    )
    for pk in operations:
        try:
            operator(actor)
            # Atomic scheduling prevents replicas repeatedly selecting the same
            # item. The business service still owns its durable lease/fencing.
            if PaymentOperation.objects.filter(pk=pk, next_check_at__lte=now).update(
                next_check_at=now + timedelta(seconds=60)
            ):
                services.reconcile_operation(
                    actor, pk, reason="Supervised lookup-only recovery", dry_run=False
                )
                result["lookups"] += 1
        except Exception:
            result["failures"] += 1
    # Lookup can itself durably receive a newly observed provider fact. Refresh
    # the cutoff so that fact is eligible in this cycle rather than stranded
    # behind the earlier selection timestamp.
    now = timezone.now()
    stale = Q(state="processing", leased_at__lte=now - timedelta(seconds=90))
    events = list(
        Inbox.objects.filter(
            provider="simulator", mode="test", account__isnull=False, next_check_at__lte=now
        )
        .filter(Q(state__in=["received", "retry"]) | stale)
        .order_by("next_check_at", "pk")
        .values_list("pk", flat=True)[:limit]
    )
    for pk in events:
        try:
            operator(actor)
            if Inbox.objects.filter(pk=pk, next_check_at__lte=now).update(
                next_check_at=now + timedelta(seconds=60)
            ):
                services.process_event(actor, pk)
                result["events"] += 1
        except Exception:
            result["failures"] += 1
    return result
