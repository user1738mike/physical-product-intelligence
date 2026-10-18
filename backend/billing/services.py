"""Provider-independent internal billing workflow; financial and access histories stay separate."""

import hashlib
import json
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from commercial import services as access
from organizations.services import ADMIN, OWNER, authorize

from . import adapter
from .models import (
    AccessGrant,
    Allocation,
    BillingAccount,
    BillingAudit,
    Inbox,
    MoneyEvent,
    PaymentOperation,
    Price,
    Statement,
    StatementAdjustment,
)

# Narrow capability whitelist verified from SIX ISO 4217 List One, 2026-10-16.
# XTS has no ISO minor unit; exponent zero below is an explicit simulator-only convention.
CURRENCIES = {"USD": 2, "EUR": 2, "JPY": 0, "KWD": 3, "KES": 2}


class Conflict(APIException):
    status_code = 409
    default_detail = "Billing operation conflicts with existing state."


def audit(actor, account, action, reference, reason):
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
        raise ValidationError("An operator reason is required (at most 500 characters).")
    BillingAudit.objects.create(
        actor=actor, account=account, action=action, reference=str(reference), reason=reason
    )


def locked_account(account):
    access.lock(account.organization)
    return (
        BillingAccount.objects.select_for_update().select_related("organization").get(pk=account.pk)
    )


def amount(value, *, zero=True, maximum=10**15):
    if type(value) is not int or not (0 if zero else 1) <= value <= maximum:
        raise ValidationError("Use bounded integer minor units.")
    return value


def currency(code, exponent, mode):
    expected = 0 if code == "XTS" and mode == "test" else CURRENCIES.get(code)
    if type(exponent) is not int or expected is None or exponent != expected:
        raise ValidationError(
            "Unsupported currency/exponent; select an explicitly supported configuration."
        )


@transaction.atomic
def enroll(org):
    access.lock(org)
    return BillingAccount.objects.get_or_create(organization=org)[0]


@transaction.atomic
def configure_simulator(actor, org, *, reason):
    access.operator(actor)
    adapter.require()
    account = enroll(org)
    locked_account(account)
    if account.mode != "test" or (account.provider and account.provider != "simulator"):
        raise Conflict()
    account.provider, account.mode = "simulator", "test"
    account.merchant, account.customer_ref = (
        "synthetic-merchant",
        "synthetic-customer-" + account.pk.hex,
    )
    account.save()
    audit(actor, account, "simulator_configured", account.pk, reason)
    return account


@transaction.atomic
def publish_price(actor, *, code, version, plan, currency_code, exponent, unit_minor, mode, reason):
    access.operator(actor)
    currency(currency_code, exponent, mode)
    amount(unit_minor, maximum=10**12)
    if type(version) is not int or version < 1 or mode not in {"test", "live"}:
        raise ValidationError("Invalid price version/mode.")
    item = Price(
        code=code,
        version=version,
        plan=plan,
        currency=currency_code,
        exponent=exponent,
        unit_minor=unit_minor,
        mode=mode,
        actor=actor,
        reason=reason,
    )
    item.full_clean()
    item.save()
    audit(actor, None, "price_published", item.pk, reason)
    return item


def sum_amount(query):
    return query.aggregate(n=Sum("amount_minor"))["n"] or 0


def settled(statement):
    return sum_amount(Allocation.objects.filter(statement=statement))


def total(statement):
    return statement.total_minor + (
        StatementAdjustment.objects.filter(statement=statement).aggregate(n=Sum("delta_minor"))["n"]
        or 0
    )


@transaction.atomic
def adjust_statement(actor, statement, *, delta_minor, operation, reason):
    access.operator(actor)
    locked_account(statement.account)
    item = Statement.objects.get(pk=statement.pk, state="finalized")
    old = StatementAdjustment.objects.filter(statement=item, operation=operation).first()
    if old:
        if (old.delta_minor, old.reason) != (delta_minor, reason):
            raise Conflict("Correction identity conflict.")
        return old
    if (
        type(delta_minor) is not int
        or not delta_minor
        or not 0 <= total(item) + delta_minor <= 10**15
        or total(item) + delta_minor < settled(item)
    ):
        raise ValidationError(
            "Correction must retain nonnegative balances and existing allocations."
        )
    correction = StatementAdjustment.objects.create(
        statement=item, operation=operation, delta_minor=delta_minor, actor=actor, reason=reason
    )
    audit(actor, item.account, "statement_adjusted", correction.pk, reason)
    return correction


@transaction.atomic
def generate(actor, account, price, *, start, end, quantity=1, access_transition=False, reason):
    access.operator(actor)
    account = locked_account(account)
    amount(quantity, zero=False, maximum=1000000)
    if (
        start.utcoffset() is None
        or end.utcoffset() is None
        or end <= start
        or account.mode != price.mode
    ):
        raise ValidationError("Statement period/mode invalid.")
    amount(price.unit_minor * quantity)
    old = Statement.objects.filter(
        account=account, mode=price.mode, period_start=start, period_end=end
    ).first()
    if old:
        if (old.price_id, old.quantity, old.access_transition) != (
            price.pk,
            quantity,
            access_transition,
        ):
            raise Conflict("Period already has a different statement.")
        return old
    item = Statement.objects.create(
        account=account,
        price=price,
        period_start=start,
        period_end=end,
        mode=price.mode,
        quantity=quantity,
        actor=actor,
        reason=reason,
        access_transition=access_transition,
    )
    audit(actor, account, "statement_generated", item.pk, reason)
    return item


@transaction.atomic
def revise(actor, statement, *, quantity, expected_version, reason):
    access.operator(actor)
    locked_account(statement.account)
    item = Statement.objects.select_for_update().get(pk=statement.pk)
    amount(quantity, zero=False, maximum=1000000)
    if item.state != "draft" or item.version != expected_version:
        raise Conflict()
    amount(item.price.unit_minor * quantity)
    item.quantity, item.reason, item.actor = quantity, reason, actor
    item.version += 1
    item.save()
    audit(actor, item.account, "draft_revised", item.pk, reason)
    return item


@transaction.atomic
def finalize(actor, statement, *, reason):
    access.operator(actor)
    locked_account(statement.account)
    item = Statement.objects.select_for_update().select_related("price__plan").get(pk=statement.pk)
    if item.state == "finalized":
        return item
    price = item.price
    item.total_minor = amount(price.unit_minor * item.quantity)
    item.snapshot = {
        "plan_id": str(price.plan_id),
        "plan_code": price.plan.code,
        "plan_version": price.plan.version,
        "price_id": str(price.pk),
        "price_version": price.version,
        "currency": price.currency,
        "exponent": price.exponent,
        "unit_minor": str(price.unit_minor),
        "quantity": item.quantity,
        "total_minor": str(item.total_minor),
        "period_start": item.period_start.isoformat(),
        "period_end": item.period_end.isoformat(),
        "basis": "fixed_price_no_usage_charges",
        "tax_policy": "unconfigured_internal_statement_not_tax_invoice",
        "access_transition_authorized": item.access_transition,
    }
    item.state, item.finalized_at = "finalized", timezone.now()
    item.save()
    audit(actor, item.account, "statement_finalized", item.pk, reason)
    return item


@transaction.atomic
def request_operation(actor, org_id, statement_id, request_id, *, partial_minor=None):
    org, _ = authorize(actor, org_id, roles={OWNER, ADMIN}, lock=True)
    try:
        statement = Statement.objects.select_related("account", "price").get(
            account__organization=org, pk=statement_id, state="finalized"
        )
    except Statement.DoesNotExist:
        raise NotFound("Statement not found.") from None
    account = statement.account
    adapter.require()
    if account.provider != "simulator" or account.mode != "test" or statement.mode != account.mode:
        raise ValidationError(
            {"code": "collection_unavailable", "detail": "Payment collection is not available."}
        )
    identity = access.fingerprint(
        {
            "statement": str(statement.pk),
            "principal": actor.pk,
            "request_id": str(request_id),
            "partial_minor": partial_minor,
        }
    )
    old = PaymentOperation.objects.filter(account=account, request_id=request_id).first()
    if old:
        if old.fingerprint != identity:
            raise Conflict("Request identity already has different billing input.")
        return old
    if PaymentOperation.objects.filter(
        statement=statement, state__in=["pending", "processing", "unknown", "ready"]
    ).exists():
        raise Conflict("An operation is already awaiting confirmation; refresh its status.")
    remaining = total(statement) - settled(statement)
    requested = remaining
    if partial_minor is not None:
        # Installments require an operator-reviewed workflow; public APIs accept no amount.
        access.operator(actor)
        requested = amount(partial_minor, zero=False)
        if requested > remaining:
            raise ValidationError("Installment exceeds remaining amount.")
    amount(requested, zero=False)
    if statement.period_end <= timezone.now():
        raise Conflict("Statement access period has ended; operator review is required.")
    operation = PaymentOperation.objects.create(
        account=account,
        statement=statement,
        principal=actor,
        request_id=request_id,
        fingerprint=identity,
        provider=account.provider,
        merchant=account.merchant,
        mode=account.mode,
        amount_minor=requested,
        currency=statement.snapshot["currency"],
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    audit(actor, account, "operation_requested", operation.pk, "Authorized fixed-price operation")
    return operation


@transaction.atomic
def claim_outbound(actor, operation_id):
    access.operator(actor)
    item = PaymentOperation.objects.select_related("statement__account__organization").get(
        pk=operation_id
    )
    locked_account(item.statement.account)
    item = PaymentOperation.objects.select_for_update().get(pk=item.pk)
    if item.state != "pending":
        return item, None
    if item.expires_at <= timezone.now():
        item.state = "expired"
        item.save(update_fields=["state"])
        return item, None
    item.state, item.lease, item.leased_at = "processing", uuid.uuid4(), timezone.now()
    item.save(update_fields=["state", "lease", "leased_at"])
    return item, item.lease


def process_outbound(actor, operation_id):
    item, lease = claim_outbound(actor, operation_id)
    if lease is None:
        return item
    try:
        external = adapter.create(item)  # No caller transaction or lock crosses provider I/O.
    except Exception:
        external = None
    with transaction.atomic():
        locked_account(item.statement.account)
        current = PaymentOperation.objects.select_for_update().get(pk=item.pk)
        if current.state != "processing" or current.lease != lease:
            return current
        current.state = "ready" if external else "unknown"
        current.external_ref = external or ""
        current.save(update_fields=["state", "external_ref"])
        audit(
            actor,
            item.statement.account,
            "outbound_" + current.state,
            current.pk,
            "Durable operation outcome; unknown requires lookup, not new submission",
        )
        return current


@transaction.atomic
def receive(body, timestamp, proof):
    data = adapter.verify(body, timestamp, proof)
    digest = access.fingerprint(data)
    # Shared advisory lock serializes repeated event identity even for unknown customer mappings.
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 91))",
            ["simulator:" + data["merchant"] + ":" + data["mode"] + ":" + data["event_id"]],
        )
    old = Inbox.objects.filter(
        provider="simulator",
        merchant=data["merchant"],
        mode=data["mode"],
        event_id=data["event_id"],
    ).first()
    if old:
        if old.semantic_sha256 != digest:
            raise Conflict("Event identity has conflicting semantic content.")
        return old
    account = BillingAccount.objects.filter(
        provider="simulator",
        merchant=data["merchant"],
        mode=data["mode"],
        customer_ref=data["customer"],
    ).first()
    return Inbox.objects.create(
        account=account,
        provider="simulator",
        merchant=data["merchant"],
        mode=data["mode"],
        event_id=data["event_id"],
        semantic_sha256=digest,
        raw_sha256=hashlib.sha256(body).hexdigest(),
        payload=data,
        state="received" if account else "quarantined",
        outcome="" if account else "unknown_account",
    )


def quarantined(event, reason):
    event.state, event.outcome = "quarantined", reason
    event.save(update_fields=["state", "outcome"])
    return event


@transaction.atomic
def claim_event(actor, event_id):
    access.operator(actor)
    adapter.require()
    event = Inbox.objects.select_related("account__organization").get(pk=event_id)
    if event.account_id is None:
        return event, None
    locked_account(event.account)
    event = Inbox.objects.select_for_update().get(pk=event.pk)
    if event.state in {"applied", "ignored", "quarantined"}:
        return event, None
    if (
        event.state == "processing"
        and event.leased_at
        and event.leased_at > timezone.now() - timedelta(seconds=90)
    ):
        return event, None
    if event.attempts >= 5:
        return quarantined(event, "attempt_limit"), None
    event.state, event.lease, event.leased_at = "processing", uuid.uuid4(), timezone.now()
    event.attempts += 1
    event.save(update_fields=["state", "lease", "leased_at", "attempts"])
    audit(
        actor, event.account, "event_processing_attempt", event.pk, "Durable inbox processing lease"
    )
    return event, event.lease


def process_event(actor, event_id):
    event, lease = claim_event(actor, event_id)
    if lease is None:
        return event
    operation = PaymentOperation.objects.filter(
        statement__account=event.account,
        provider=event.provider,
        merchant=event.merchant,
        mode=event.mode,
        external_ref=event.payload["object_ref"],
    ).first()
    try:
        obj = adapter.lookup(operation) if operation else None
        return _apply_event(actor, event_id, lease, obj)
    except Exception:
        # Durable retry state contains a fixed category, never provider bodies or private payloads.
        with transaction.atomic():
            current = Inbox.objects.select_for_update().get(pk=event_id)
            if current.lease == lease and current.state == "processing":
                current.state, current.outcome = "retry", "processing_interrupted"
                current.save(update_fields=["state", "outcome"])
            return current


@transaction.atomic
def _apply_event(actor, event_id, lease, obj):
    access.operator(actor)
    adapter.require()
    event = Inbox.objects.select_related("account__organization").get(pk=event_id)
    if event.account_id is None:
        return event
    account = locked_account(event.account)
    event = Inbox.objects.select_for_update().get(pk=event.pk)
    if event.state != "processing" or event.lease != lease:
        return event
    p = event.payload
    operation = (
        PaymentOperation.objects.select_related("statement__account", "statement__price__plan")
        .filter(
            statement__account=account,
            provider=event.provider,
            merchant=event.merchant,
            mode=event.mode,
            external_ref=p["object_ref"],
        )
        .first()
    )
    if operation is None:
        return quarantined(event, "unmapped_object")
    if p["kind"] not in {
        "payment.succeeded",
        "payment.failed",
        "subscription.cancelled",
        "refund.observed",
        "dispute.observed",
    }:
        event.state, event.outcome = "ignored", "unsupported_event"
        event.save(update_fields=["state", "outcome"])
        return event
    if not obj or obj.operation_id != operation.pk or obj.version != p["object_version"]:
        return quarantined(event, "ambiguous_object_version")
    statement = operation.statement
    expected = {
        "price_id": str(statement.price_id),
        "period_start": statement.period_start.isoformat(),
        "period_end": statement.period_end.isoformat(),
        "currency": operation.currency,
    }
    if (
        any(p[k] != v for k, v in expected.items())
        or account.mode != "test"
        or statement.mode != event.mode
    ):
        return quarantined(event, "statement_scope_mismatch")
    if p["kind"] == "payment.succeeded":
        if (
            obj.state != "paid"
            or obj.amount_minor != p["amount_minor"]
            or obj.currency != p["currency"]
        ):
            return quarantined(event, "authoritative_state_mismatch")
        old = MoneyEvent.objects.filter(account=account, effect_id=p["effect_id"]).first()
        if old:
            if (
                old.kind != "payment"
                or old.operation_id != operation.pk
                or old.amount_minor != p["amount_minor"]
                or old.currency != p["currency"]
            ):
                return quarantined(event, "conflicting_effect")
        else:
            old = MoneyEvent.objects.create(
                account=account,
                inbox=event,
                operation=operation,
                effect_id=p["effect_id"],
                kind="payment",
                amount_minor=amount(p["amount_minor"], zero=False),
                currency=operation.currency,
            )
        if p["amount_minor"] != operation.amount_minor:
            return quarantined(event, "amount_mismatch_unapplied_credit")
        if operation.expires_at <= timezone.now():
            return quarantined(event, "late_confirmation_unapplied_credit")
        if not Allocation.objects.filter(money=old).exists():
            available = total(statement) - settled(statement)
            if old.amount_minor > available:
                return quarantined(event, "excess_unapplied_credit")
            Allocation.objects.create(statement=statement, money=old, amount_minor=old.amount_minor)
        operation.state = "succeeded"
        if (
            settled(statement) == total(statement)
            and statement.access_transition
            and not AccessGrant.objects.filter(statement=statement).exists()
        ):
            if statement.period_end <= timezone.now():
                return quarantined(event, "late_settlement_access_review")
            assignment = access.assign(
                actor,
                account.organization,
                statement.price.plan,
                reason="Verified synthetic settlement " + str(event.pk),
                starts_at=max(timezone.now(), statement.period_start),
                ends_at=statement.period_end,
                source="verified_payment",
            )
            AccessGrant.objects.create(statement=statement, event=event, assignment=assignment)
    elif p["kind"] == "refund.observed":
        if obj.state != "refunded":
            return quarantined(event, "authoritative_state_mismatch")
        original = MoneyEvent.objects.filter(
            account=account,
            operation=operation,
            effect_id=p["reverses"],
            kind="payment",
            currency=operation.currency,
        ).first()
        if original is None:
            return quarantined(event, "missing_original_receipt")
        existing = MoneyEvent.objects.filter(account=account, effect_id=p["effect_id"]).first()
        if existing:
            if existing.reverses_id != original.pk or existing.amount_minor != -p["amount_minor"]:
                return quarantined(event, "conflicting_effect")
        else:
            refunded = -sum_amount(MoneyEvent.objects.filter(reverses=original))
            if p["amount_minor"] <= 0 or refunded + p["amount_minor"] > original.amount_minor:
                return quarantined(event, "refund_amount_mismatch")
            refund = MoneyEvent.objects.create(
                account=account,
                inbox=event,
                operation=operation,
                effect_id=p["effect_id"],
                kind="refund",
                amount_minor=-p["amount_minor"],
                currency=operation.currency,
                reverses=original,
            )
            allocation = Allocation.objects.filter(money=original, reverses__isnull=True).first()
            if allocation:
                remaining = allocation.amount_minor + sum_amount(
                    Allocation.objects.filter(reverses=allocation)
                )
                if remaining:
                    Allocation.objects.create(
                        statement=statement,
                        money=refund,
                        amount_minor=-min(remaining, p["amount_minor"]),
                        reverses=allocation,
                    )
        event.outcome = "observed_refund_access_review_required"
    elif p["kind"] == "payment.failed":
        if obj.state != "failed":
            return quarantined(event, "authoritative_state_mismatch")
        operation.state = "failed"
    elif p["kind"] == "subscription.cancelled":
        if obj.state != "cancelled":
            return quarantined(event, "authoritative_state_mismatch")
        operation.state = "cancelled"
        event.outcome = "no_renewal_existing_access_ends_as_assigned"
    else:
        if obj.state != "disputed":
            return quarantined(event, "authoritative_state_mismatch")
        event.outcome = "dispute_observed_access_review_required"
    operation.provider_version = max(operation.provider_version, p["object_version"])
    operation.save(update_fields=["state", "provider_version"])
    event.state = "applied"
    event.save(update_fields=["state", "outcome"])
    audit(
        actor,
        account,
        "event_applied",
        event.pk,
        event.outcome or "Verified synthetic business event",
    )
    return event


def reconcile_operation(actor, operation_id, *, reason, dry_run=True):
    access.operator(actor)
    item = PaymentOperation.objects.select_related("statement__account__organization").get(
        pk=operation_id
    )
    if dry_run:
        return {
            "operation": str(item.pk),
            "state": item.state,
            "action": "lookup_only_no_resubmission",
            "dry_run": True,
        }
    with transaction.atomic():
        locked_account(item.statement.account)
        item = PaymentOperation.objects.select_for_update().get(pk=item.pk)
        if (
            item.state == "processing"
            and item.leased_at
            and item.leased_at > timezone.now() - timedelta(seconds=90)
        ):
            return {"operation": str(item.pk), "state": item.state, "action": "lease_active"}
        item.lease = uuid.uuid4()
        item.save(update_fields=["lease"])
    obj = adapter.lookup(item)
    return _finish_reconciliation(actor, item, obj, reason)


@transaction.atomic
def _finish_reconciliation(actor, previous, obj, reason):
    locked_account(previous.statement.account)
    item = PaymentOperation.objects.select_for_update().get(pk=previous.pk)
    if item.lease != previous.lease:
        return {"operation": str(item.pk), "state": item.state, "action": "fenced"}
    if obj:
        item.external_ref = obj.external_ref
        if item.state in {"processing", "unknown"}:
            item.state = "ready"
    elif item.state in {"processing", "unknown"}:
        item.state = "unknown"
    elif item.state == "pending" and item.expires_at <= timezone.now():
        item.state = "expired"
    item.save(update_fields=["lease", "external_ref", "state"])
    if obj and obj.state in {"paid", "failed", "cancelled", "disputed"}:
        kind = {
            "paid": "payment.succeeded",
            "failed": "payment.failed",
            "cancelled": "subscription.cancelled",
            "disputed": "dispute.observed",
        }[obj.state]
        data = adapter.payload(
            item, obj, kind=kind, event_id="lookup-" + obj.external_ref + "-" + str(obj.version)
        )
        body = json.dumps(data, sort_keys=True).encode()
        timestamp, proof = adapter.sign(body)
        receive(body, timestamp, proof)
    audit(actor, item.statement.account, "operation_reconciled", item.pk, reason)
    return {
        "operation": str(item.pk),
        "state": item.state,
        "action": "lookup_only_no_resubmission",
        "dry_run": False,
    }


def statement_data(statement):
    paid = settled(statement)
    action_required = (
        Inbox.objects.filter(
            account=statement.account,
            state="quarantined",
            payload__price_id=str(statement.price_id),
        ).exists()
        or Inbox.objects.filter(
            account=statement.account,
            state="applied",
            outcome__in=[
                "observed_refund_access_review_required",
                "dispute_observed_access_review_required",
            ],
            payload__price_id=str(statement.price_id),
        ).exists()
    )
    effective = total(statement)
    state = (
        "draft"
        if statement.state == "draft"
        else "settled"
        if paid == effective
        else "partially_settled"
        if paid
        else "pending"
    )
    return {
        "id": statement.pk,
        "status": "action_required" if action_required else state,
        "settlement_status": state,
        "period_start": statement.period_start,
        "period_end": statement.period_end,
        "currency": statement.snapshot.get("currency", statement.price.currency),
        "exponent": statement.snapshot.get("exponent", statement.price.exponent),
        "total_minor": str(effective),
        "original_total_minor": str(statement.total_minor),
        "settled_minor": str(paid),
        "remaining_minor": str(effective - paid),
        "snapshot": statement.snapshot,
        "mode": statement.mode,
        "access_fulfilled": AccessGrant.objects.filter(statement=statement).exists(),
        "corrections": [
            {"id": item.pk, "delta_minor": str(item.delta_minor), "created_at": item.created_at}
            for item in StatementAdjustment.objects.filter(statement=statement).order_by(
                "created_at"
            )
        ],
        "settlements": [
            {
                "id": item.pk,
                "kind": item.money.kind,
                "amount_minor": str(item.amount_minor),
                "created_at": item.created_at,
            }
            for item in Allocation.objects.filter(statement=statement)
            .select_related("money")
            .order_by("created_at")
        ],
        "download_path": (
            f"/api/v1/organizations/{statement.account.organization_id}/billing/"
            f"statements/{statement.pk}/download/"
        ),
    }


def account_summary(actor, org_id):
    org, _ = authorize(actor, org_id, roles={OWNER, ADMIN}, allow_suspended=True)
    account = BillingAccount.objects.filter(organization=org).first()
    if account is None:
        return {
            "collection_available": False,
            "statements": [],
            "operations": [],
            "unapplied_credit": {},
        }
    statements = (
        Statement.objects.filter(account=account)
        .select_related("price")
        .order_by("-created_at")[:50]
    )
    credit = {}
    for code in (
        MoneyEvent.objects.filter(account=account).values_list("currency", flat=True).distinct()
    ):
        credit[code] = str(
            sum_amount(MoneyEvent.objects.filter(account=account, currency=code))
            - sum_amount(
                Allocation.objects.filter(statement__account=account, money__currency=code)
            )
        )
    return {
        "collection_available": False,
        "statements": [statement_data(s) for s in statements],
        "operations": [
            {
                "id": o.pk,
                "statement_id": o.statement_id,
                "status": o.state,
                "amount_minor": str(o.amount_minor),
                "currency": o.currency,
                "expires_at": o.expires_at,
            }
            for o in PaymentOperation.objects.filter(statement__account=account).order_by(
                "-created_at"
            )[:50]
        ],
        "unapplied_credit": credit,
    }
