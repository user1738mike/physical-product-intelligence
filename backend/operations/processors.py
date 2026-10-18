"""Bounded maintenance cycles; never initiate AI requests or payment operations."""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from integrations import services as integrations
from integrations.models import Delivery

from commercial import services as commercial
from ingestion.models import ImportJob
from ingestion.retention import cycle as retention_cycle
from operations.models import RateBucket


def operator(actor):
    actor.refresh_from_db(fields=["is_active", "is_staff"])
    commercial.operator(actor)


def cycle(actor, *, limit=20):
    operator(actor)
    if not 1 <= limit <= 100:
        raise ValueError("Cycle limit must be 1..100")
    result = {"deliveries": 0, "recovered": 0, "counters": 0, "failures": 0}
    now = timezone.now()
    # Each lane fails independently. Existing services own tenant locks, permission
    # checks, immutable audit and fencing; no transaction encloses network work.
    if integrations.available():
        ids = list(
            Delivery.objects.filter(due_at__lte=now)
            .filter(
                Q(state__in=["pending", "retryable"]) | Q(state="claimed", lease_until__lte=now)
            )
            .order_by("due_at", "pk")
            .values_list("pk", flat=True)[:limit]
        )
        for pk in ids:
            try:
                operator(actor)
                integrations.dispatch_one(pk)
                result["deliveries"] += 1
            except Exception:
                result["failures"] += 1
    stale = list(
        ImportJob.objects.filter(
            mode="ai", status="processing", started_at__lte=now - timedelta(seconds=90)
        )
        .select_related("organization")
        .order_by("started_at", "pk")[:limit]
    )
    for job in stale:
        try:
            operator(actor)
            result["recovered"] += commercial.recover(
                actor, job.organization, reason="Supervised abandoned-work recovery", limit=1
            )
        except Exception:
            result["failures"] += 1
    ids = list(
        RateBucket.objects.filter(expires_at__lt=now)
        .order_by("expires_at", "pk")
        .values_list("pk", flat=True)[:500]
    )
    operator(actor)
    result["counters"] = RateBucket.objects.filter(pk__in=ids, expires_at__lt=now).delete()[0]
    removed = retention_cycle(actor, limit=limit)
    result["removed"] = removed["removed"]
    result["failures"] += removed["failures"]
    return result
