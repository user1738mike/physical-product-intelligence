import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Now
from django.utils import timezone

from products.models import Snapshot


class BillingAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField("organizations.Organization", on_delete=models.PROTECT)
    provider = models.CharField(max_length=20, default="")
    merchant = models.CharField(max_length=100, default="")
    mode = models.CharField(max_length=8, default="test")
    customer_ref = models.CharField(max_length=120, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "merchant", "mode", "customer_ref"],
                condition=~Q(provider=""),
                name="billing_customer_scope",
            ),
            models.CheckConstraint(
                condition=Q(mode__in=["test", "live"]), name="billing_account_mode"
            ),
        ]


class Price(Snapshot):
    code = models.SlugField(max_length=60)
    version = models.PositiveIntegerField()
    plan = models.ForeignKey("commercial.Plan", on_delete=models.PROTECT)
    currency = models.CharField(max_length=3)
    exponent = models.PositiveSmallIntegerField()
    unit_minor = models.BigIntegerField()
    mode = models.CharField(max_length=8)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="billing_price_version"),
            models.CheckConstraint(
                condition=Q(
                    version__gt=0,
                    exponent__lte=3,
                    unit_minor__gte=0,
                    unit_minor__lte=10**12,
                    mode__in=["test", "live"],
                ),
                name="billing_price_bounds",
            ),
        ]


class Statement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(BillingAccount, on_delete=models.PROTECT)
    price = models.ForeignKey(Price, on_delete=models.PROTECT)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    mode = models.CharField(max_length=8)
    state = models.CharField(max_length=12, default="draft")
    version = models.PositiveIntegerField(default=1)
    quantity = models.PositiveIntegerField(default=1)
    total_minor = models.BigIntegerField(default=0)
    snapshot = models.JSONField(default=dict)
    access_transition = models.BooleanField(default=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(default=timezone.now)
    finalized_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "mode", "period_start", "period_end"],
                name="billing_statement_period",
            ),
            models.CheckConstraint(
                condition=Q(
                    period_end__gt=F("period_start"),
                    quantity__gt=0,
                    quantity__lte=1000000,
                    total_minor__gte=0,
                    total_minor__lte=10**15,
                    mode__in=["test", "live"],
                    state__in=["draft", "finalized"],
                ),
                name="billing_statement_bounds",
            ),
        ]


class PaymentOperation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    statement = models.ForeignKey(Statement, on_delete=models.PROTECT)
    account = models.ForeignKey(BillingAccount, on_delete=models.PROTECT)
    principal = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    provider = models.CharField(max_length=20)
    merchant = models.CharField(max_length=100)
    mode = models.CharField(max_length=8)
    amount_minor = models.BigIntegerField()
    currency = models.CharField(max_length=3)
    state = models.CharField(max_length=16, default="pending")
    lease = models.UUIDField(null=True)
    leased_at = models.DateTimeField(null=True)
    expires_at = models.DateTimeField()
    external_ref = models.CharField(max_length=120, default="")
    provider_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    next_check_at = models.DateTimeField(default=timezone.now, db_default=Now(), db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "request_id"], name="billing_operation_request"
            ),
            models.CheckConstraint(
                condition=Q(
                    amount_minor__gt=0,
                    amount_minor__lte=10**15,
                    mode__in=["test", "live"],
                    state__in=[
                        "pending",
                        "processing",
                        "unknown",
                        "ready",
                        "succeeded",
                        "failed",
                        "cancelled",
                        "expired",
                    ],
                ),
                name="billing_operation_bounds",
            ),
        ]


class Inbox(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(BillingAccount, null=True, on_delete=models.PROTECT)
    provider = models.CharField(max_length=20)
    merchant = models.CharField(max_length=100)
    mode = models.CharField(max_length=8)
    event_id = models.CharField(max_length=120)
    semantic_sha256 = models.CharField(max_length=64)
    raw_sha256 = models.CharField(max_length=64)
    payload = models.JSONField()
    state = models.CharField(max_length=16, default="received")
    outcome = models.CharField(max_length=80, default="")
    attempts = models.PositiveIntegerField(default=0)
    lease = models.UUIDField(null=True)
    leased_at = models.DateTimeField(null=True)
    received_at = models.DateTimeField(default=timezone.now)
    next_check_at = models.DateTimeField(default=timezone.now, db_default=Now(), db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "merchant", "mode", "event_id"], name="billing_event_identity"
            )
        ]


class MoneyEvent(Snapshot):
    account = models.ForeignKey(BillingAccount, on_delete=models.PROTECT)
    inbox = models.ForeignKey(Inbox, on_delete=models.PROTECT)
    operation = models.ForeignKey(PaymentOperation, on_delete=models.PROTECT)
    effect_id = models.CharField(max_length=120)
    kind = models.CharField(max_length=16)
    amount_minor = models.BigIntegerField()
    currency = models.CharField(max_length=3)
    reverses = models.ForeignKey("self", null=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "effect_id"], name="billing_effect_identity"
            ),
            models.CheckConstraint(
                condition=Q(kind="payment", amount_minor__gt=0, reverses__isnull=True)
                | Q(kind="refund", amount_minor__lt=0, reverses__isnull=False),
                name="billing_money_kind",
            ),
        ]


class Allocation(Snapshot):
    statement = models.ForeignKey(Statement, on_delete=models.PROTECT)
    money = models.ForeignKey(MoneyEvent, on_delete=models.PROTECT)
    amount_minor = models.BigIntegerField()
    reverses = models.ForeignKey("self", null=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["statement", "money"], name="billing_allocation_once"),
            models.CheckConstraint(
                condition=Q(amount_minor__gt=0, reverses__isnull=True)
                | Q(amount_minor__lt=0, reverses__isnull=False),
                name="billing_allocation_kind",
            ),
        ]


class AccessGrant(Snapshot):
    statement = models.OneToOneField(Statement, on_delete=models.PROTECT)
    event = models.ForeignKey(Inbox, on_delete=models.PROTECT)
    assignment = models.ForeignKey("commercial.Assignment", on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)


class BillingAudit(Snapshot):
    account = models.ForeignKey(BillingAccount, null=True, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    action = models.CharField(max_length=60)
    reference = models.CharField(max_length=120)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(default=timezone.now)


class GatewayObject(models.Model):
    """Isolated simulator state only; never evidence for live collection."""

    operation = models.OneToOneField(PaymentOperation, primary_key=True, on_delete=models.PROTECT)
    external_ref = models.CharField(max_length=120, unique=True)
    version = models.PositiveIntegerField(default=1)
    state = models.CharField(max_length=20, default="pending")
    amount_minor = models.BigIntegerField()
    currency = models.CharField(max_length=3)


class GatewayCall(Snapshot):
    operation = models.ForeignKey(PaymentOperation, on_delete=models.PROTECT)
    action = models.CharField(max_length=20)
    created_at = models.DateTimeField(default=timezone.now)


class StatementAdjustment(Snapshot):
    statement = models.ForeignKey(Statement, on_delete=models.PROTECT)
    operation = models.UUIDField()
    delta_minor = models.BigIntegerField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["statement", "operation"], name="billing_adjustment_identity"
            ),
            models.CheckConstraint(
                condition=~Q(delta_minor=0)
                & Q(delta_minor__gte=-(10**15), delta_minor__lte=10**15),
                name="billing_adjustment_amount",
            ),
        ]
