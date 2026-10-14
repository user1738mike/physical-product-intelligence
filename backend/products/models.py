import uuid

from django.conf import settings
from django.db import models


def finite_decimal_bounds(original, canonical):
    """Numeric NaN sorts above finite PostgreSQL numbers; upper checks exclude it too."""
    condition = models.Q()
    for field, limit in [(name, 10**12) for name in original] + [
        (name, 10**15) for name in canonical
    ]:
        condition &= models.Q(**{field + "__isnull": True}) | models.Q(**{field + "__lt": limit})
    return condition


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
        indexes = [
            models.Index(
                fields=["organization", "is_active", "updated_at"], name="product_org_state_updated"
            )
        ]
        constraints = [
            models.UniqueConstraint(fields=["organization", "sku"], name="product_org_sku")
        ]


class Evidence(Snapshot):
    class SourceType(models.TextChoices):
        MANUAL = "manual", "Manual observation"
        SUPPLIER = "supplier_document", "Supplier document"
        TEST = "physical_test", "Physical test"
        MANUFACTURER = "manufacturer_spec", "Manufacturer specification"
        IMPORT = "imported_catalog", "Imported catalog"
        ESTIMATE = "ai_estimate", "AI or model estimate"
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
                    source_type__in=[
                        "manual",
                        "supplier_document",
                        "physical_test",
                        "other",
                        "manufacturer_spec",
                        "imported_catalog",
                        "ai_estimate",
                    ]
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
                condition=finite_decimal_bounds(
                    ["original_value", "original_lower", "original_upper"],
                    ["canonical_value", "canonical_lower", "canonical_upper"],
                ),
                name="measurement_finite_values",
            ),
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


class PackagingConfiguration(models.Model):
    """Stable, editable packaging identity; prior revision snapshots remain separate history."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="configurations")
    name = models.CharField(max_length=160)
    level = models.CharField(max_length=10, choices=PackagingProfile.Level.choices)
    quantity = models.PositiveIntegerField(null=True)
    material = models.CharField(max_length=200, blank=True)
    description = models.CharField(max_length=2000, blank=True)
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_packaging",
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="modified_packaging",
    )

    class Meta:
        ordering = ["name", "id"]
        indexes = [models.Index(fields=["product", "is_active"], name="packaging_product_state")]
        constraints = [
            models.UniqueConstraint(fields=["product", "name"], name="packaging_product_name"),
            models.CheckConstraint(
                condition=models.Q(level__in=["unit", "inner", "case", "pallet"]),
                name="configuration_valid_level",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__isnull=True) | models.Q(quantity__gte=1),
                name="configuration_positive_count",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1), name="configuration_positive_version"
            ),
        ]


class ConfigurationRevision(Snapshot):
    packaging = models.ForeignKey(
        PackagingConfiguration, on_delete=models.PROTECT, related_name="revisions"
    )
    version = models.PositiveIntegerField()
    name = models.CharField(max_length=160)
    level = models.CharField(max_length=10, choices=PackagingProfile.Level.choices)
    quantity = models.PositiveIntegerField(null=True)
    material = models.CharField(max_length=200, blank=True)
    description = models.CharField(max_length=2000, blank=True)
    is_active = models.BooleanField()
    change_reason = models.CharField(max_length=1000)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["packaging", "version"], name="configuration_revision_number"
            )
        ]


NUMERIC_ATTRIBUTES = ["length", "width", "height", "mass"]
TEXT_ATTRIBUTES = ["name", "brand", "manufacturer", "category", "material"]
ATTRIBUTES = NUMERIC_ATTRIBUTES + TEXT_ATTRIBUTES


class AttributeClaim(Snapshot):
    class Basis(models.TextChoices):
        REPORTED = "reported", "Reported"
        ESTIMATED = "estimated", "Estimated"
        MEASURED = "measured", "Physically verified (attested)"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="claims")
    packaging = models.ForeignKey(
        PackagingConfiguration, null=True, on_delete=models.PROTECT, related_name="claims"
    )
    attribute = models.CharField(max_length=20, choices=[(v, v) for v in ATTRIBUTES])
    basis = models.CharField(max_length=10, choices=Basis.choices)
    value = models.DecimalField(max_digits=18, decimal_places=6, null=True)
    unit = models.CharField(max_length=4, blank=True)
    lower = models.DecimalField(max_digits=18, decimal_places=6, null=True)
    upper = models.DecimalField(max_digits=18, decimal_places=6, null=True)
    canonical_value = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    canonical_unit = models.CharField(max_length=4, blank=True)
    canonical_lower = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    canonical_upper = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    text_value = models.CharField(max_length=2000, blank=True)
    conversion_version = models.CharField(max_length=30, default="metric-v1")
    evidence = models.ForeignKey(Evidence, on_delete=models.PROTECT)
    method = models.CharField(max_length=2000, blank=True)
    limitations = models.CharField(max_length=2000, blank=True)
    observed_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        indexes = [
            models.Index(
                fields=["product", "packaging", "attribute"], name="claim_resource_attribute"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=finite_decimal_bounds(
                    ["value", "lower", "upper"],
                    ["canonical_value", "canonical_lower", "canonical_upper"],
                ),
                name="claim_finite_values",
            ),
            models.CheckConstraint(
                condition=models.Q(basis__in=["reported", "estimated", "measured"]),
                name="claim_valid_basis",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        attribute__in=NUMERIC_ATTRIBUTES,
                        value__gt=0,
                        value__isnull=False,
                        canonical_value__gt=0,
                        canonical_value__isnull=False,
                        text_value="",
                    )
                    | models.Q(
                        attribute__in=TEXT_ATTRIBUTES,
                        value__isnull=True,
                        canonical_value__isnull=True,
                        unit="",
                        canonical_unit="",
                        lower__isnull=True,
                        upper__isnull=True,
                        canonical_lower__isnull=True,
                        canonical_upper__isnull=True,
                    )
                    & ~models.Q(text_value="")
                ),
                name="claim_typed_value",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(attribute="mass", unit__in=["g", "kg"], canonical_unit="kg")
                    | models.Q(
                        attribute__in=["length", "width", "height"],
                        unit__in=["mm", "cm", "m"],
                        canonical_unit="mm",
                    )
                    | models.Q(attribute__in=TEXT_ATTRIBUTES, unit="", canonical_unit="")
                ),
                name="claim_compatible_units",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        lower__isnull=True,
                        upper__isnull=True,
                        canonical_lower__isnull=True,
                        canonical_upper__isnull=True,
                    )
                    | models.Q(
                        lower__isnull=False,
                        upper__isnull=False,
                        canonical_lower__isnull=False,
                        canonical_upper__isnull=False,
                        lower__gt=0,
                        lower__lte=models.F("value"),
                        upper__gte=models.F("value"),
                        canonical_lower__gt=0,
                        canonical_lower__lte=models.F("canonical_value"),
                        canonical_upper__gte=models.F("canonical_value"),
                    )
                ),
                name="claim_valid_bounds",
            ),
            models.CheckConstraint(
                condition=~models.Q(basis="estimated")
                | (~models.Q(method="") & ~models.Q(limitations="")),
                name="claim_estimate_explained",
            ),
        ]


class ClaimVerification(Snapshot):
    claim = models.ForeignKey(
        AttributeClaim, on_delete=models.PROTECT, related_name="verifications"
    )
    measured_claim = models.OneToOneField(
        AttributeClaim, on_delete=models.PROTECT, related_name="verification_record"
    )
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    verified_at = models.DateTimeField(auto_now_add=True)
    instrument = models.CharField(max_length=200)
    procedure = models.CharField(max_length=2000)
    notes = models.CharField(max_length=2000)

    class Meta:
        ordering = ["-verified_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(claim=models.F("measured_claim")),
                name="verification_distinct_claim",
            )
        ]


class ClaimSelection(Snapshot):
    claim = models.ForeignKey(AttributeClaim, on_delete=models.PROTECT, related_name="selections")
    selected_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    selected_at = models.DateTimeField(auto_now_add=True)
    rationale = models.CharField(max_length=2000)

    class Meta:
        ordering = ["-selected_at", "-id"]
