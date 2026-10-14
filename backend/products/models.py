import uuid

from django.conf import settings
from django.db import models


class ImmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Product history is immutable; create a new record")

    def delete(self):
        raise ValueError("Product history cannot be deleted")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValueError("Product history is immutable; create a new record")


class Snapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    objects = ImmutableQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Product history is immutable; create a new record")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Product history cannot be deleted")


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    sku = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sku", "id"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "sku"], name="product_org_sku")
        ]


class Evidence(Snapshot):
    class SourceType(models.TextChoices):
        MANUAL = "manual", "Manual observation"
        SUPPLIER = "supplier_document", "Supplier document"
        TEST = "physical_test", "Physical test"
        OTHER = "other", "Other reference"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="evidence")
    title = models.CharField(max_length=200)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    source_reference = models.CharField(max_length=2000)
    description = models.TextField(blank=True)
    # A caller's declared digest, never a claim that an artifact was fetched or verified.
    declared_sha256 = models.CharField(max_length=64, blank=True)
    attribution = models.CharField(max_length=200)
    license = models.CharField(max_length=200)
    observed_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    source_type__in=["manual", "supplier_document", "physical_test", "other"]
                ),
                name="evidence_valid_source",
            )
        ]


class ProductRevision(Snapshot):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="revisions")
    number = models.PositiveIntegerField()
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    brand = models.CharField(max_length=160, blank=True)
    manufacturer = models.CharField(max_length=160, blank=True)
    model_number = models.CharField(max_length=160, blank=True)
    category = models.CharField(max_length=160, blank=True)
    change_reason = models.CharField(max_length=1000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-number", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "number"], name="product_revision_number"),
            models.CheckConstraint(
                condition=models.Q(number__gte=1), name="revision_positive_number"
            ),
        ]


class RevisionEvidence(Snapshot):
    revision = models.ForeignKey(ProductRevision, on_delete=models.PROTECT, related_name="sources")
    evidence = models.ForeignKey(Evidence, on_delete=models.PROTECT)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["revision", "evidence"], name="revision_evidence_unique"
            )
        ]


class PackagingProfile(Snapshot):
    class Level(models.TextChoices):
        UNIT = "unit", "Unit"
        INNER = "inner", "Inner pack"
        CASE = "case", "Case"
        PALLET = "pallet", "Pallet"

    revision = models.ForeignKey(
        ProductRevision, on_delete=models.PROTECT, related_name="packaging"
    )
    level = models.CharField(max_length=10, choices=Level.choices)
    contains = models.ForeignKey("self", null=True, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    material = models.CharField(max_length=200, blank=True)
    notes = models.CharField(max_length=2000, blank=True)
    # Null represents unknown, rather than silently asserting a handling characteristic.
    fragile = models.BooleanField(null=True)
    stackable = models.BooleanField(null=True)

    class Meta:
        ordering = ["level", "id"]
        constraints = [
            models.UniqueConstraint(fields=["revision", "level"], name="packaging_revision_level"),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1), name="packaging_positive_count"
            ),
            models.CheckConstraint(
                condition=models.Q(level__in=["unit", "inner", "case", "pallet"]),
                name="packaging_valid_level",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(level="unit", contains__isnull=True, quantity=1)
                    | (~models.Q(level="unit") & models.Q(contains__isnull=False))
                ),
                name="packaging_root_or_container",
            ),
        ]


class Measurement(Snapshot):
    class Property(models.TextChoices):
        LENGTH = "length", "Length"
        WIDTH = "width", "Width"
        HEIGHT = "height", "Height"
        MASS = "mass", "Mass"

    class Method(models.TextChoices):
        MEASURED = "measured", "Measured"
        SUPPLIER = "supplier_specification", "Supplier specification"
        MANUAL = "manual_transcription", "Manual transcription"

    packaging = models.ForeignKey(
        PackagingProfile, on_delete=models.PROTECT, related_name="measurements"
    )
    property = models.CharField(max_length=10, choices=Property.choices)
    original_value = models.DecimalField(max_digits=18, decimal_places=6)
    original_unit = models.CharField(max_length=4)
    original_lower = models.DecimalField(max_digits=18, decimal_places=6, null=True)
    original_upper = models.DecimalField(max_digits=18, decimal_places=6, null=True)
    canonical_value = models.DecimalField(max_digits=24, decimal_places=9)
    canonical_unit = models.CharField(max_length=4)
    canonical_lower = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    canonical_upper = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    conversion_version = models.CharField(max_length=30, default="metric-v1")
    method = models.CharField(max_length=30, choices=Method.choices)
    observed_at = models.DateTimeField()
    evidence = models.ForeignKey(Evidence, on_delete=models.PROTECT)

    class Meta:
        ordering = ["property", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(original_value__gt=0, canonical_value__gt=0),
                name="measurement_positive_values",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(property="mass", original_unit__in=["g", "kg"], canonical_unit="kg")
                    | models.Q(
                        property__in=["length", "width", "height"],
                        original_unit__in=["mm", "cm", "m"],
                        canonical_unit="mm",
                    )
                ),
                name="measurement_compatible_units",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        original_lower__isnull=True,
                        original_upper__isnull=True,
                        canonical_lower__isnull=True,
                        canonical_upper__isnull=True,
                    )
                    | models.Q(
                        original_lower__gt=0,
                        original_lower__lte=models.F("original_value"),
                        original_upper__gte=models.F("original_value"),
                        canonical_lower__gt=0,
                        canonical_lower__lte=models.F("canonical_value"),
                        canonical_upper__gte=models.F("canonical_value"),
                        original_lower__isnull=False,
                        original_upper__isnull=False,
                        canonical_lower__isnull=False,
                        canonical_upper__isnull=False,
                    )
                ),
                name="measurement_valid_bounds",
            ),
        ]
