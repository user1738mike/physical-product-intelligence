from decimal import Decimal

from rest_framework import serializers

from accounts.serializers import StrictSerializer
from organizations.serializers import PageSerializer
from products.serializers import CONVERSIONS, decimal_field

from .models import Assessment, Equipment, EquipmentRevision, RuleActivation, RuleSet

ATTRIBUTES = ["length", "width", "height", "mass"]
LEVELS = ["unit", "inner", "case", "pallet"]
ORIENTATIONS = ["as_recorded", "swap_length_width"]
DEFINITION_FIELDS = [
    "name",
    "description",
    "manufacturer",
    "model",
    "category",
    "source_reference",
    "operational_context",
    "supported_levels",
    "orientation_notes",
    "handling_notes",
]


class DefinitionInput(StrictSerializer):
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=2000, allow_blank=True, default="")
    manufacturer = serializers.CharField(max_length=160, allow_blank=True, default="")
    model = serializers.CharField(max_length=160, allow_blank=True, default="")
    category = serializers.ChoiceField(
        choices=[
            "conveyor",
            "storage",
            "tote_bin",
            "shelving",
            "picking_cell",
            "gripper",
            "handling",
        ]
    )
    source_reference = serializers.CharField(max_length=1000, allow_blank=True, default="")
    operational_context = serializers.CharField(max_length=2000, allow_blank=True, default="")
    supported_levels = serializers.ListField(
        child=serializers.ChoiceField(choices=LEVELS), max_length=4, default=list
    )
    orientation_notes = serializers.CharField(max_length=1000, allow_blank=True, default="")
    handling_notes = serializers.CharField(max_length=2000, allow_blank=True, default="")

    def validate_supported_levels(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Packaging levels must be distinct.")
        return value


class EquipmentInput(DefinitionInput):
    code = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", max_length=100)


class EquipmentEdit(DefinitionInput):
    expected_version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(min_length=5, max_length=1000)

    def get_fields(self):
        fields = super().get_fields()
        for name, field in fields.items():
            if name in DEFINITION_FIELDS:
                field.required = False
                field.default = serializers.empty
        return fields

    def validate(self, data):
        if not set(data) & set(DEFINITION_FIELDS):
            raise serializers.ValidationError("Provide at least one equipment field.")
        return data


class EquipmentState(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(choices=["draft", "archived"])
    reason = serializers.CharField(min_length=5, max_length=1000)


class SourceInput(StrictSerializer):
    kind = serializers.ChoiceField(choices=["evidence", "import"])
    id = serializers.UUIDField()


class RuleInput(StrictSerializer):
    id = serializers.UUIDField()
    type = serializers.ChoiceField(
        choices=["maximum", "minimum", "required_attribute", "packaging_level", "orientation"]
    )
    name = serializers.CharField(max_length=160)
    explanation = serializers.CharField(min_length=5, max_length=1000)
    severity = serializers.ChoiceField(choices=["hard", "advisory"])
    enabled = serializers.BooleanField()
    attribute = serializers.ChoiceField(choices=ATTRIBUTES, required=False)
    limit = decimal_field(required=False)
    unit = serializers.ChoiceField(choices=list(CONVERSIONS), required=False)
    margin = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal("0"), required=False
    )
    allowed = serializers.ListField(
        child=serializers.CharField(max_length=32), max_length=4, required=False
    )
    source_reference = serializers.CharField(max_length=1000, allow_blank=True, default="")
    source = SourceInput(required=False, allow_null=True, default=None)

    def validate(self, data):
        kind = data["type"]
        operands = set(data) & {"attribute", "limit", "unit", "margin", "allowed"}
        if kind in {"maximum", "minimum"}:
            if not {"attribute", "limit", "unit"} <= operands or "allowed" in operands:
                raise serializers.ValidationError(
                    "Numeric rules need attribute, positive limit and compatible unit; "
                    "allowed is unsupported."
                )
            factor, canonical = CONVERSIONS[data["unit"]]
            if (data["attribute"] == "mass") != (canonical == "kg"):
                raise serializers.ValidationError("Rule unit is incompatible with its attribute.")
            data.setdefault("margin", Decimal("0"))
            if kind == "maximum" and data["margin"] >= data["limit"]:
                raise serializers.ValidationError(
                    "Maximum clearance must be smaller than the limit."
                )
            data["canonical_limit"] = str(data["limit"] * factor)
            data["canonical_margin"] = str(data["margin"] * factor)
            data["canonical_unit"] = canonical
        elif kind == "required_attribute":
            if operands != {"attribute"}:
                raise serializers.ValidationError(
                    "Required-attribute rules take only a numeric attribute."
                )
        else:
            choices = LEVELS if kind == "packaging_level" else ORIENTATIONS
            if (
                operands != {"allowed"}
                or not data["allowed"]
                or set(data["allowed"]) - set(choices)
            ):
                raise serializers.ValidationError(
                    "Supply a nonempty allowlisted set of allowed values only."
                )
            if len(set(data["allowed"])) != len(data["allowed"]):
                raise serializers.ValidationError("Allowed values must be distinct.")
        return data


class RuleSetInput(StrictSerializer):
    expected_equipment_version = serializers.IntegerField(min_value=1)
    expected_rule_version = serializers.IntegerField(min_value=0)
    name = serializers.CharField(max_length=160)
    reason = serializers.CharField(min_length=5, max_length=1000)
    evidence_policy = serializers.ChoiceField(choices=["reported_or_measured", "measured_only"])
    rules = RuleInput(many=True, min_length=1, max_length=30)

    def validate_rules(self, rules):
        if len({rule["id"] for rule in rules}) != len(rules):
            raise serializers.ValidationError("Rule identifiers must be unique in the rule set.")
        return rules


class ActivationInput(StrictSerializer):
    expected_equipment_version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(min_length=10, max_length=1000)


class AssessmentInput(StrictSerializer):
    request_id = serializers.UUIDField()
    product_id = serializers.UUIDField()
    packaging_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    equipment_id = serializers.UUIDField()
    rule_set_id = serializers.UUIDField()
    orientation = serializers.ChoiceField(
        choices=ORIENTATIONS, required=False, allow_null=True, default=None
    )
    product_level = serializers.ChoiceField(
        choices=LEVELS, required=False, allow_null=True, default=None
    )
    parent_id = serializers.UUIDField(required=False, allow_null=True, default=None)

    def validate(self, data):
        if data["packaging_id"] and data["product_level"]:
            raise serializers.ValidationError(
                "A package's level is derived from its profile, not overridden."
            )
        return data


class PageQuery(StrictSerializer):
    page = serializers.IntegerField(min_value=1, max_value=100000, default=1)


class EquipmentQuery(PageQuery):
    search = serializers.CharField(max_length=100, allow_blank=True, default="")
    status = serializers.ChoiceField(choices=["draft", "active", "archived"], required=False)
    category = serializers.ChoiceField(
        choices=DefinitionInput().fields["category"].choices, required=False
    )


class AssessmentQuery(PageQuery):
    product_id = serializers.UUIDField(required=False)
    equipment_id = serializers.UUIDField(required=False)
    overall = serializers.ChoiceField(
        choices=["compatible", "incompatible", "indeterminate"], required=False
    )
    date_from = serializers.DateTimeField(required=False)
    date_to = serializers.DateTimeField(required=False)

    def validate(self, data):
        if data.get("date_from") and data.get("date_to") and data["date_from"] > data["date_to"]:
            raise serializers.ValidationError("Start date must precede end date.")
        return data


class EquipmentSerializer(serializers.ModelSerializer):
    revision = serializers.IntegerField(read_only=True)
    revision_id = serializers.UUIDField(read_only=True)
    definition = serializers.JSONField(read_only=True)
    latest_rule_version = serializers.IntegerField(read_only=True)

    class Meta:
        model = Equipment
        fields = [
            "id",
            "organization_id",
            "code",
            "status",
            "version",
            "revision",
            "revision_id",
            "definition",
            "latest_rule_version",
            "created_by_id",
            "modified_by_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class EquipmentRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EquipmentRevision
        fields = [
            "id",
            "equipment_id",
            "number",
            "definition",
            "reason",
            "created_by_id",
            "created_at",
        ]
        read_only_fields = fields


class ActivationSerializer(serializers.ModelSerializer):
    class Meta:
        model = RuleActivation
        fields = ["id", "activated_by_id", "activated_at", "reason"]
        read_only_fields = fields


class RuleSetSerializer(serializers.ModelSerializer):
    activation = ActivationSerializer(read_only=True, allow_null=True)

    class Meta:
        model = RuleSet
        fields = [
            "id",
            "equipment_id",
            "equipment_revision_id",
            "number",
            "name",
            "rules",
            "evidence_policy",
            "schema_version",
            "reason",
            "created_by_id",
            "created_at",
            "activation",
        ]
        read_only_fields = fields


class AssessmentSummary(serializers.ModelSerializer):
    class Meta:
        model = Assessment
        fields = [
            "id",
            "product_id",
            "packaging_id",
            "equipment_id",
            "equipment_revision_id",
            "product_revision_id",
            "rule_set_id",
            "parent_id",
            "created_by_id",
            "created_at",
            "engine_version",
            "overall",
            "summary",
        ]
        read_only_fields = fields


class AssessmentSerializer(AssessmentSummary):
    class Meta(AssessmentSummary.Meta):
        fields = AssessmentSummary.Meta.fields + [
            "organization_id",
            "request_id",
            "packaging_revision_id",
            "inputs",
            "equipment_snapshot",
            "rule_snapshot",
            "results",
        ]
        read_only_fields = fields


class EquipmentPage(PageSerializer):
    results = EquipmentSerializer(many=True)


class EquipmentRevisionPage(PageSerializer):
    results = EquipmentRevisionSerializer(many=True)


class RuleSetPage(PageSerializer):
    results = RuleSetSerializer(many=True)


class AssessmentPage(PageSerializer):
    results = AssessmentSummary(many=True)
