import uuid

from django.conf import settings
from django.db import models

from products.models import Snapshot


class ImportJob(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "uploaded"
        VALIDATING = "validating"
        PROCESSING = "processing"
        REVIEW = "awaiting_review"
        COMPLETED = "completed"
        ERRORS = "completed_with_errors"
        FAILED = "failed"
        CANCELLED = "cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    storage_key = models.CharField(max_length=200)
    display_name = models.CharField(max_length=120)
    format = models.CharField(max_length=8)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    scan_status = models.CharField(max_length=16, default="unscanned")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.UPLOADED)
    version = models.PositiveIntegerField(default=1)
    parser_version = models.CharField(max_length=80, default="bounded-v1")
    options = models.JSONField(default=dict)
    preview = models.JSONField(default=dict)
    mapping = models.JSONField(default=dict)
    counters = models.JSONField(default=dict)
    errors = models.JSONField(default=list)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["organization", "status"], name="import_org_status")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "uploaded",
                        "validating",
                        "processing",
                        "awaiting_review",
                        "completed",
                        "completed_with_errors",
                        "failed",
                        "cancelled",
                    ]
                ),
                name="import_valid_status",
            )
        ]


class ImportRow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(ImportJob, on_delete=models.PROTECT, related_name="rows")
    number = models.PositiveIntegerField()
    location = models.CharField(max_length=160)
    raw = models.JSONField(default=dict)
    sku = models.CharField(max_length=100, blank=True)
    product = models.ForeignKey("products.Product", null=True, on_delete=models.PROTECT)
    expected_revision = models.PositiveIntegerField(null=True)
    packaging = models.ForeignKey(
        "products.PackagingConfiguration", null=True, on_delete=models.PROTECT
    )
    expected_packaging_version = models.PositiveIntegerField(null=True)
    allow_create = models.BooleanField(default=False)
    errors = models.JSONField(default=list)
    applied = models.BooleanField(default=False)
    evidence = models.ForeignKey("products.Evidence", null=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ["number", "id"]
        constraints = [models.UniqueConstraint(fields=["job", "number"], name="import_job_row")]


class Candidate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    row = models.ForeignKey(ImportRow, on_delete=models.PROTECT, related_name="candidates")
    field = models.CharField(max_length=32)
    raw_value = models.CharField(max_length=2000)
    proposed = models.JSONField(default=dict)
    normalized = models.JSONField(default=dict)
    existing = models.JSONField(default=list)
    quality = models.CharField(max_length=16)
    errors = models.JSONField(default=list)
    decision = models.CharField(max_length=16, default="pending")
    select_value = models.BooleanField(default=False)
    reason = models.CharField(max_length=1000, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(null=True)
    version = models.PositiveIntegerField(default=1)
    claim = models.ForeignKey("products.AttributeClaim", null=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ["row__number", "field", "id"]
        constraints = [
            models.UniqueConstraint(fields=["row", "field"], name="import_row_field"),
            models.CheckConstraint(
                condition=models.Q(decision__in=["pending", "approve", "reject"]),
                name="candidate_valid_decision",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    quality__in=["new", "equivalent", "duplicate", "conflict", "invalid"]
                ),
                name="candidate_valid_quality",
            ),
        ]


class ReviewRecord(Snapshot):
    job = models.ForeignKey(ImportJob, on_delete=models.PROTECT, related_name="reviews")
    candidate = models.ForeignKey(Candidate, null=True, on_delete=models.PROTECT)
    row = models.ForeignKey(ImportRow, null=True, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=32)
    reason = models.CharField(max_length=1000)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)

    class Meta:
        ordering = ["-at", "-id"]
