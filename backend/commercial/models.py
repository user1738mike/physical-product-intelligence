import uuid

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import F, Func, Q, Value
from django.utils import timezone

from products.models import Snapshot

FEATURES = ("catalog_write", "evidence_import", "equipment_write", "assessments", "ai_extraction")
METERS = ("active_products", "assessments", "extractions")


class Plan(Snapshot):
    code = models.SlugField(max_length=60)
    version = models.PositiveIntegerField()
    name = models.CharField(max_length=100)
    catalog_write = models.BooleanField(default=True)
    evidence_import = models.BooleanField(default=True)
    equipment_write = models.BooleanField(default=True)
    assessments = models.BooleanField(default=True)
    ai_extraction = models.BooleanField(default=True)
    active_products_limit = models.PositiveIntegerField(null=True)
    assessments_limit = models.PositiveIntegerField(null=True)
    extractions_limit = models.PositiveIntegerField(null=True)
    published_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="commercial_plan_version"),
            models.CheckConstraint(condition=Q(version__gt=0), name="commercial_plan_positive"),
        ]


class Assignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=12, default="active")
    source = models.CharField(max_length=30, default="manual_pilot")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["active", "suspended"]), name="commercial_assignment_status"
            ),
            models.CheckConstraint(
                condition=Q(ends_at__isnull=True) | Q(ends_at__gt=F("starts_at")),
                name="commercial_assignment_period",
            ),
            ExclusionConstraint(
                name="commercial_assignment_no_overlap",
                expressions=[
                    ("organization", RangeOperators.EQUAL),
                    (
                        Func(
                            F("starts_at"),
                            F("ends_at"),
                            Value("[)"),
                            function="TSTZRANGE",
                            output_field=DateTimeRangeField(),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ],
            ),
        ]


class AssignmentEvent(Snapshot):
    assignment = models.ForeignKey(Assignment, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    action = models.CharField(max_length=24)
    reason = models.CharField(max_length=500)
    state = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)


class Account(models.Model):
    organization = models.OneToOneField(
        "organizations.Organization", primary_key=True, on_delete=models.PROTECT
    )
    metering_started_at = models.DateTimeField(default=timezone.now)


class Reservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    assignment = models.ForeignKey(Assignment, on_delete=models.PROTECT)
    meter = models.CharField(max_length=20)
    operation = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    state = models.CharField(max_length=12, default="reserved")
    fence = models.CharField(max_length=64, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "meter", "operation"], name="commercial_operation_identity"
            ),
            models.CheckConstraint(
                condition=Q(state__in=["reserved", "finalized", "released"]),
                name="commercial_reservation_state",
            ),
            models.CheckConstraint(
                condition=Q(meter__in=["assessments", "extractions"]),
                name="commercial_reservation_meter",
            ),
            models.CheckConstraint(
                condition=Q(period_end__gt=F("period_start")), name="commercial_reservation_period"
            ),
        ]


class Usage(Snapshot):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    reservation = models.OneToOneField(Reservation, null=True, on_delete=models.PROTECT)
    adjustment_of = models.ForeignKey("self", null=True, on_delete=models.PROTECT)
    assignment = models.ForeignKey(Assignment, on_delete=models.PROTECT)
    operation = models.UUIDField(default=uuid.uuid4)
    meter = models.CharField(max_length=20)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    amount = models.IntegerField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "meter", "operation"], name="commercial_usage_operation"
            ),
            models.CheckConstraint(
                condition=Q(reservation__isnull=False, adjustment_of__isnull=True, amount=1)
                | (Q(reservation__isnull=True, adjustment_of__isnull=False) & ~Q(amount=0)),
                name="commercial_usage_kind",
            ),
            models.CheckConstraint(
                condition=Q(meter__in=["assessments", "extractions"]), name="commercial_usage_meter"
            ),
            models.CheckConstraint(
                condition=Q(period_end__gt=F("period_start")), name="commercial_usage_period"
            ),
        ]


class ReservationEvent(Snapshot):
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT)
    assignment = models.ForeignKey(Assignment, on_delete=models.PROTECT)
    state = models.CharField(max_length=12)
    fence = models.CharField(max_length=64)
    reason = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)


class OperatorEvent(Snapshot):
    organization = models.ForeignKey(
        "organizations.Organization", null=True, on_delete=models.PROTECT
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=30)
    reason = models.CharField(max_length=500)
    reference = models.CharField(max_length=64, default="")
    created_at = models.DateTimeField(default=timezone.now)
