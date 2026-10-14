from decimal import Decimal

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from accounts.serializers import StrictSerializer
from organizations.serializers import PageSerializer

from .models import Evidence, Measurement, PackagingProfile, Product, ProductRevision

LEVELS = ["unit", "inner", "case", "pallet"]
CONVERSIONS = {
    "mm": (Decimal("1"), "mm"),
    "cm": (Decimal("10"), "mm"),
    "m": (Decimal("1000"), "mm"),
    "g": (Decimal("0.001"), "kg"),
    "kg": (Decimal("1"), "kg"),
}


class ObservationTimeField(serializers.DateTimeField):
    def to_internal_value(self, value):
        observed = super().to_internal_value(value)
        if observed > timezone.now():
            raise serializers.ValidationError("Observation time cannot be in the future.")
        return observed


def decimal_field(**kwargs):
    return serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal("0.000001"), **kwargs
    )


class MeasurementInput(StrictSerializer):
    property = serializers.ChoiceField(choices=Measurement.Property.choices)
    value = decimal_field()
    unit = serializers.ChoiceField(choices=list(CONVERSIONS))
    lower = decimal_field(required=False, allow_null=True, default=None)
    upper = decimal_field(required=False, allow_null=True, default=None)
    method = serializers.ChoiceField(choices=Measurement.Method.choices)
    observed_at = ObservationTimeField()
    evidence_id = serializers.UUIDField()

    def validate(self, data):
        _, canonical_unit = CONVERSIONS[data["unit"]]
        if (data["property"] == "mass") != (canonical_unit == "kg"):
            raise serializers.ValidationError("Unit is incompatible with the measured property.")
        lower, upper = data["lower"], data["upper"]
        if (lower is None) != (upper is None):
            raise serializers.ValidationError("Provide both uncertainty bounds or neither.")
        if lower is not None and not lower <= data["value"] <= upper:
            raise serializers.ValidationError("Bounds must enclose the reported value.")
        return data


class PackagingInput(StrictSerializer):
    level = serializers.ChoiceField(choices=PackagingProfile.Level.choices)
    contains_level = serializers.ChoiceField(
        choices=PackagingProfile.Level.choices, required=False, allow_null=True, default=None
    )
    quantity = serializers.IntegerField(min_value=1, max_value=1_000_000)
    material = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    fragile = serializers.BooleanField(required=False, allow_null=True, default=None)
    stackable = serializers.BooleanField(required=False, allow_null=True, default=None)
    measurements = MeasurementInput(many=True, max_length=50, required=False, default=list)


class RevisionInput(StrictSerializer):
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(
        max_length=8000, required=False, allow_blank=True, default=""
    )
    brand = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    manufacturer = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    model_number = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    category = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    change_reason = serializers.CharField(max_length=1000)
    evidence_ids = serializers.ListField(
        child=serializers.UUIDField(), max_length=100, required=False, default=list
    )
    packaging = PackagingInput(many=True, max_length=4, required=False, default=list)

    def validate(self, data):
        profiles = {profile["level"]: profile for profile in data["packaging"]}
        if len(profiles) != len(data["packaging"]):
            raise serializers.ValidationError("Packaging levels must be unique within a revision.")
        if profiles and "unit" not in profiles:
            raise serializers.ValidationError("Packaging requires a unit root.")
        for level, profile in profiles.items():
            contained = profile["contains_level"]
            if level == "unit":
                if contained is not None or profile["quantity"] != 1:
                    raise serializers.ValidationError(
                        "The unit root contains no level and has quantity 1."
                    )
            elif contained not in profiles or LEVELS.index(contained) >= LEVELS.index(level):
                raise serializers.ValidationError(
                    "Containers must reference a smaller level in this revision."
                )
        if len(set(data["evidence_ids"])) != len(data["evidence_ids"]):
            raise serializers.ValidationError("Evidence references must be unique.")
        return data


class ProductCreateInput(StrictSerializer):
    sku = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", max_length=100)
    revision = RevisionInput()


class ProductStateInput(StrictSerializer):
    is_active = serializers.BooleanField()


class EvidenceInput(StrictSerializer):
    title = serializers.CharField(max_length=200)
    source_type = serializers.ChoiceField(choices=Evidence.SourceType.choices)
    source_reference = serializers.CharField(max_length=2000)
    description = serializers.CharField(
        max_length=4000, required=False, allow_blank=True, default=""
    )
    declared_sha256 = serializers.RegexField(
        r"^[a-f0-9]{64}$", required=False, allow_blank=True, default=""
    )
    attribution = serializers.CharField(max_length=200)
    license = serializers.CharField(max_length=200)
    observed_at = ObservationTimeField()


class ProductSerializer(serializers.ModelSerializer):
    latest_revision_number = serializers.IntegerField(read_only=True)
    latest_revision_id = serializers.UUIDField(read_only=True)
    creator_id = serializers.IntegerField(read_only=True, allow_null=True)
    modified_by_id = serializers.IntegerField(read_only=True, allow_null=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    brand = serializers.CharField(read_only=True)
    manufacturer = serializers.CharField(read_only=True)
    model_number = serializers.CharField(read_only=True)
    category = serializers.CharField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "organization_id",
            "sku",
            "is_active",
            "latest_revision_number",
            "latest_revision_id",
            "name",
            "description",
            "brand",
            "manufacturer",
            "model_number",
            "category",
            "creator_id",
            "modified_by_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ArtifactSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    sha256 = serializers.CharField()
    location = serializers.CharField()
    download_path = serializers.CharField()


class EvidenceSerializer(serializers.ModelSerializer):
    capture_status = serializers.SerializerMethodField()
    source_artifact = serializers.SerializerMethodField()

    @extend_schema_field(ArtifactSerializer(allow_null=True))
    def get_source_artifact(self, obj):
        row = obj.importrow_set.select_related("job").first()
        if row is None:
            return None
        return {
            "job_id": str(row.job_id),
            "sha256": row.job.sha256,
            "location": row.location,
            "download_path": (
                f"/api/v1/organizations/{row.job.organization_id}/imports/{row.job_id}/file/"
            ),
        }

    def get_capture_status(self, obj) -> str:
        return "stored_private" if obj.importrow_set.exists() else "reference_only"

    class Meta:
        model = Evidence
        fields = [
            "id",
            "product_id",
            "title",
            "source_type",
            "source_reference",
            "description",
            "declared_sha256",
            "capture_status",
            "source_artifact",
            "attribution",
            "license",
            "observed_at",
            "recorded_at",
            "recorded_by_id",
        ]
        read_only_fields = fields


class MeasurementSerializer(serializers.ModelSerializer):
    verification_status = serializers.SerializerMethodField()

    def get_verification_status(self, obj) -> str:
        # A contributor-declared method is not an authorized physical verification.
        return "unverified_report"

    class Meta:
        model = Measurement
        fields = [
            "id",
            "property",
            "original_value",
            "original_unit",
            "original_lower",
            "original_upper",
            "canonical_value",
            "canonical_unit",
            "canonical_lower",
            "canonical_upper",
            "conversion_version",
            "method",
            "observed_at",
            "evidence_id",
            "verification_status",
        ]
        read_only_fields = fields


class PackagingSerializer(serializers.ModelSerializer):
    measurements = MeasurementSerializer(many=True, read_only=True)

    class Meta:
        model = PackagingProfile
        fields = [
            "id",
            "revision_id",
            "level",
            "contains_id",
            "quantity",
            "material",
            "notes",
            "fragile",
            "stackable",
            "measurements",
        ]
        read_only_fields = fields


class RevisionSerializer(serializers.ModelSerializer):
    packaging = PackagingSerializer(many=True, read_only=True)
    evidence_ids = serializers.SerializerMethodField()

    @extend_schema_field(serializers.ListField(child=serializers.UUIDField()))
    def get_evidence_ids(self, obj):
        return [source.evidence_id for source in obj.sources.all()]

    class Meta:
        model = ProductRevision
        fields = [
            "id",
            "product_id",
            "number",
            "name",
            "description",
            "brand",
            "manufacturer",
            "model_number",
            "category",
            "change_reason",
            "created_by_id",
            "created_at",
            "evidence_ids",
            "packaging",
        ]
        read_only_fields = fields


class ProductPage(PageSerializer):
    results = ProductSerializer(many=True, read_only=True)


class RevisionPage(PageSerializer):
    results = RevisionSerializer(many=True, read_only=True)


class EvidencePage(PageSerializer):
    results = EvidenceSerializer(many=True, read_only=True)


class PackagingPage(PageSerializer):
    results = PackagingSerializer(many=True, read_only=True)
