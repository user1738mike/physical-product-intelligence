import uuid

from django.conf import settings
from django.db import models

from products.models import Snapshot


class Equipment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    code = models.CharField(max_length=100)
    status = models.CharField(max_length=16, default="draft")
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_equipment",
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="modified_equipment",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code", "id"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="equipment_org_code"),
            models.CheckConstraint(
                condition=models.Q(status__in=["draft", "active", "archived"]),
                name="equipment_valid_status",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1), name="equipment_positive_version"
            ),
        ]
        indexes = [models.Index(fields=["organization", "status"], name="equipment_org_status")]


class EquipmentRevision(Snapshot):
    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT, related_name="revisions")
    number = models.PositiveIntegerField()
    definition = models.JSONField()
    reason = models.CharField(max_length=1000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-number", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["equipment", "number"], name="equipment_revision_number"
            )
        ]


class RuleSet(Snapshot):
    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT, related_name="rule_sets")
    equipment_revision = models.ForeignKey(EquipmentRevision, on_delete=models.PROTECT)
    number = models.PositiveIntegerField()
    name = models.CharField(max_length=160)
    rules = models.JSONField()
    evidence_policy = models.CharField(max_length=24)
    schema_version = models.CharField(max_length=40, default="warehouse-rules-v1")
    reason = models.CharField(max_length=1000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-number", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["equipment", "number"], name="equipment_ruleset_number"
            ),
            models.CheckConstraint(
                condition=models.Q(evidence_policy__in=["reported_or_measured", "measured_only"]),
                name="ruleset_evidence_policy",
            ),
        ]


class RuleActivation(Snapshot):
    rule_set = models.OneToOneField(RuleSet, on_delete=models.PROTECT, related_name="activation")
    activated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    activated_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=1000)


class Assessment(Snapshot):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT)
    product_revision = models.ForeignKey("products.ProductRevision", on_delete=models.PROTECT)
    packaging = models.ForeignKey(
        "products.PackagingConfiguration", null=True, on_delete=models.PROTECT
    )
    packaging_revision = models.ForeignKey(
        "products.ConfigurationRevision", null=True, on_delete=models.PROTECT
    )
    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT)
    equipment_revision = models.ForeignKey(EquipmentRevision, on_delete=models.PROTECT)
    rule_set = models.ForeignKey(RuleSet, on_delete=models.PROTECT)
    parent = models.ForeignKey("self", null=True, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    request_sha256 = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    engine_version = models.CharField(max_length=40, default="warehouse-fit-v1")
    overall = models.CharField(max_length=20)
    summary = models.CharField(max_length=1000)
    inputs = models.JSONField()
    equipment_snapshot = models.JSONField()
    rule_snapshot = models.JSONField()
    results = models.JSONField()

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "request_id"], name="assessment_org_request"
            ),
            models.CheckConstraint(
                condition=models.Q(overall__in=["compatible", "incompatible", "indeterminate"]),
                name="assessment_valid_result",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "created_at"], name="assessment_org_created"),
            models.Index(
                fields=["organization", "product", "created_at"], name="assessment_org_product"
            ),
            models.Index(
                fields=["organization", "equipment", "created_at"], name="assessment_org_equipment"
            ),
            models.Index(
                fields=["organization", "overall", "created_at"], name="assessment_org_result"
            ),
        ]
