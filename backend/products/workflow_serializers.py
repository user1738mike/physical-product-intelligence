from rest_framework import serializers

from accounts.serializers import StrictSerializer
from organizations.serializers import PageSerializer

from .models import (
    ATTRIBUTES,
    NUMERIC_ATTRIBUTES,
    AttributeClaim,
    ClaimSelection,
    ClaimVerification,
    ConfigurationRevision,
    PackagingConfiguration,
    PackagingProfile,
)
from .serializers import (
    CONVERSIONS,
    EvidenceInput,
    EvidenceSerializer,
    MeasurementInput,
    ObservationTimeField,
    RevisionInput,
    decimal_field,
)


class CatalogQuery(StrictSerializer):
    search = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=["all", "active", "archived"], required=False, default="all"
    )
    ordering = serializers.ChoiceField(
        choices=["sku", "-sku", "name", "-name", "updated_at", "-updated_at"],
        required=False,
        default="sku",
    )
    page = serializers.IntegerField(min_value=1, max_value=100000, required=False, default=1)


class ProductEditInput(RevisionInput):
    expected_revision = serializers.IntegerField(min_value=1)
    packaging = None
    evidence_ids = None

    def get_fields(self):
        fields = super().get_fields()
        fields.pop("packaging", None)
        fields.pop("evidence_ids", None)
        for name, field in fields.items():
            if name not in {"expected_revision", "change_reason"}:
                field.required = False
                field.default = serializers.empty
        return fields

    def validate(self, data):
        if not set(data) - {"expected_revision", "change_reason"}:
            raise serializers.ValidationError("Provide at least one product field to change.")
        return data


class ConfigurationInput(StrictSerializer):
    name = serializers.CharField(max_length=160)
    level = serializers.ChoiceField(choices=PackagingProfile.Level.choices)
    quantity = serializers.IntegerField(
        min_value=1, max_value=1000000, allow_null=True, required=False, default=None
    )
    material = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")
    description = serializers.CharField(
        max_length=2000, allow_blank=True, required=False, default=""
    )


class ConfigurationEditInput(ConfigurationInput):
    expected_version = serializers.IntegerField(min_value=1)
    change_reason = serializers.CharField(max_length=1000)

    def get_fields(self):
        fields = super().get_fields()
        for name, field in fields.items():
            if name not in {"expected_version", "change_reason"}:
                field.required = False
                field.default = serializers.empty
        return fields

    def validate(self, data):
        if not set(data) - {"expected_version", "change_reason"}:
            raise serializers.ValidationError("Provide at least one packaging field to change.")
        return data


class ConfigurationStateInput(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1)
    is_active = serializers.BooleanField()


class ConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PackagingConfiguration
        fields = [
            "id",
            "product_id",
            "name",
            "level",
            "quantity",
            "material",
            "description",
            "is_active",
            "version",
            "created_at",
            "updated_at",
            "created_by_id",
            "modified_by_id",
        ]
        read_only_fields = fields


class ConfigurationPage(PageSerializer):
    results = ConfigurationSerializer(many=True, read_only=True)


class ConfigurationRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigurationRevision
        fields = [
            "id",
            "packaging_id",
            "version",
            "name",
            "level",
            "quantity",
            "material",
            "description",
            "is_active",
            "change_reason",
            "changed_by_id",
            "recorded_at",
        ]
        read_only_fields = fields


class ConfigurationRevisionPage(PageSerializer):
    results = ConfigurationRevisionSerializer(many=True, read_only=True)


class SourceReferenceInput(StrictSerializer):
    evidence_id = serializers.UUIDField(required=False)
    source = EvidenceInput(required=False)

    def validate(self, data):
        if ("evidence_id" in data) == ("source" in data):
            raise serializers.ValidationError(
                "Provide either an existing evidence_id or a new source, exclusively."
            )
        return data


class ClaimInput(SourceReferenceInput):
    attribute = serializers.ChoiceField(choices=ATTRIBUTES)
    basis = serializers.ChoiceField(choices=["reported", "estimated"])
    value = decimal_field(required=False, allow_null=True, default=None)
    unit = serializers.ChoiceField(
        choices=list(CONVERSIONS), required=False, allow_blank=True, default=""
    )
    lower = decimal_field(required=False, allow_null=True, default=None)
    upper = decimal_field(required=False, allow_null=True, default=None)
    text_value = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )
    observed_at = ObservationTimeField()
    method = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    limitations = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )

    def validate(self, data):
        super().validate(data)
        if data["attribute"] in NUMERIC_ATTRIBUTES:
            if data["value"] is None or not data["unit"] or data["text_value"]:
                raise serializers.ValidationError(
                    "Numeric claims require a value and explicit unit, without text_value."
                )
            measurement = MeasurementInput(
                data={
                    "property": data["attribute"],
                    "value": data["value"],
                    "unit": data["unit"],
                    "lower": data["lower"],
                    "upper": data["upper"],
                    "method": "manual_transcription",
                    "observed_at": data["observed_at"],
                    "evidence_id": data.get("evidence_id", "00000000-0000-0000-0000-000000000000"),
                }
            )
            measurement.is_valid(raise_exception=True)
        elif (
            not data["text_value"]
            or data["value"] is not None
            or data["unit"]
            or data["lower"] is not None
            or data["upper"] is not None
        ):
            raise serializers.ValidationError(
                "Text claims require text_value and no numeric fields or units."
            )
        if data["basis"] == "estimated" and (not data["method"] or not data["limitations"]):
            raise serializers.ValidationError(
                "Estimates require methodology and limitations; "
                "confidence scores are not comparable."
            )
        return data


class VerificationInput(SourceReferenceInput):
    value = decimal_field()
    unit = serializers.ChoiceField(choices=list(CONVERSIONS))
    lower = decimal_field(required=False, allow_null=True, default=None)
    upper = decimal_field(required=False, allow_null=True, default=None)
    observed_at = ObservationTimeField()
    instrument = serializers.CharField(max_length=200)
    procedure = serializers.CharField(min_length=10, max_length=2000)
    notes = serializers.CharField(min_length=10, max_length=2000)


class SelectionInput(StrictSerializer):
    claim_id = serializers.UUIDField()
    rationale = serializers.CharField(min_length=10, max_length=2000)


class VerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClaimVerification
        fields = [
            "id",
            "claim_id",
            "measured_claim_id",
            "verified_by_id",
            "verified_at",
            "instrument",
            "procedure",
            "notes",
        ]
        read_only_fields = fields


class ClaimSerializer(serializers.ModelSerializer):
    evidence = EvidenceSerializer(read_only=True)
    verification_record = VerificationSerializer(read_only=True, allow_null=True)
    verifications = VerificationSerializer(many=True, read_only=True)

    class Meta:
        model = AttributeClaim
        fields = [
            "id",
            "product_id",
            "packaging_id",
            "attribute",
            "basis",
            "value",
            "unit",
            "lower",
            "upper",
            "canonical_value",
            "canonical_unit",
            "canonical_lower",
            "canonical_upper",
            "text_value",
            "conversion_version",
            "method",
            "limitations",
            "observed_at",
            "recorded_at",
            "recorded_by_id",
            "evidence",
            "verification_record",
            "verifications",
        ]
        read_only_fields = fields


class ClaimPage(PageSerializer):
    results = ClaimSerializer(many=True, read_only=True)


class SelectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClaimSelection
        fields = ["id", "claim_id", "selected_by_id", "selected_at", "rationale"]
        read_only_fields = fields


class AttributeStateSerializer(serializers.Serializer):
    attribute = serializers.CharField()
    status = serializers.ChoiceField(
        choices=["unknown", "reported", "estimated", "verified", "conflict", "resolved"]
    )
    claim_count = serializers.IntegerField()
    conflicting = serializers.BooleanField()
    selected_claim = ClaimSerializer(allow_null=True)
    selection = SelectionSerializer(allow_null=True)


class AttributeStatesSerializer(serializers.Serializer):
    results = AttributeStateSerializer(many=True)
