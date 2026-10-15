from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from accounts.serializers import StrictSerializer
from organizations.serializers import PageSerializer

from .models import Candidate, ImportJob, ImportRow, ReviewRecord

FIELDS = [
    "sku",
    "name",
    "description",
    "brand",
    "manufacturer",
    "package_name",
    "package_type",
    "material",
    "quantity",
    "length",
    "width",
    "height",
    "mass",
    "dimension_unit",
    "mass_unit",
]
NUMERIC = {"length", "width", "height", "mass"}
PRODUCT_FIELDS = {"name", "description", "brand", "manufacturer"}


@extend_schema_field(OpenApiTypes.BINARY)
class UploadFileField(serializers.FileField):
    pass


class UploadInput(StrictSerializer):
    file = UploadFileField()


class VersionInput(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1)


class EmptyInput(StrictSerializer):
    pass


class OptionsInput(VersionInput):
    sheet = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    header_row = serializers.IntegerField(min_value=1, max_value=20, required=False, default=1)
    delimiter = serializers.ChoiceField(
        choices=["", ",", ";", "\t", "|"], required=False, default=""
    )


class MappingInput(VersionInput):
    mapping = serializers.DictField(child=serializers.CharField(max_length=80))

    def validate_mapping(self, value):
        if set(value) - set(FIELDS) or "sku" not in value:
            raise serializers.ValidationError("Map SKU and allowlisted fields only.")
        if len(set(value.values())) != len(value):
            raise serializers.ValidationError("A source column may map to only one field.")
        return value


class DecisionInput(VersionInput):
    decision = serializers.ChoiceField(choices=["approve", "reject"])
    reason = serializers.CharField(min_length=5, max_length=1000)
    value = serializers.CharField(max_length=2000, required=False)
    unit = serializers.CharField(max_length=4, required=False, allow_blank=True)
    select_value = serializers.BooleanField(default=False)


class CreationInput(StrictSerializer):
    allow_create = serializers.BooleanField()
    reason = serializers.CharField(min_length=5, max_length=1000)


class JobSerializer(serializers.ModelSerializer):
    duplicate_upload_ids = serializers.SerializerMethodField()

    def get_duplicate_upload_ids(self, obj) -> list[str]:
        return [
            str(pk)
            for pk in ImportJob.objects.filter(organization=obj.organization, sha256=obj.sha256)
            .exclude(pk=obj.pk)
            .values_list("pk", flat=True)[:5]
        ]

    class Meta:
        model = ImportJob
        fields = [
            "id",
            "organization_id",
            "created_by_id",
            "created_at",
            "started_at",
            "completed_at",
            "display_name",
            "format",
            "size",
            "sha256",
            "scan_status",
            "status",
            "version",
            "parser_version",
            "options",
            "preview",
            "mapping",
            "counters",
            "errors",
            "duplicate_upload_ids",
            "mode",
            "source_job_id",
            "request_id",
            "extraction",
        ]
        read_only_fields = fields


class CandidateSerializer(serializers.ModelSerializer):
    location = serializers.CharField(source="row.location", read_only=True)
    sku = serializers.CharField(source="row.sku", read_only=True)

    class Meta:
        model = Candidate
        fields = [
            "id",
            "row_id",
            "sku",
            "location",
            "field",
            "raw_value",
            "proposed",
            "normalized",
            "existing",
            "quality",
            "errors",
            "decision",
            "select_value",
            "reason",
            "reviewed_by_id",
            "reviewed_at",
            "version",
            "claim_id",
            "extraction",
        ]
        read_only_fields = fields


class RowSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRow
        fields = [
            "id",
            "number",
            "location",
            "raw",
            "sku",
            "product_id",
            "expected_revision",
            "packaging_id",
            "expected_packaging_version",
            "allow_create",
            "errors",
            "applied",
            "evidence_id",
        ]
        read_only_fields = fields


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewRecord
        fields = [
            "id",
            "job_id",
            "candidate_id",
            "row_id",
            "actor_id",
            "at",
            "action",
            "reason",
            "before",
            "after",
        ]
        read_only_fields = fields


class JobPage(PageSerializer):
    results = JobSerializer(many=True)


class CandidatePage(PageSerializer):
    results = CandidateSerializer(many=True)


class RowPage(PageSerializer):
    results = RowSerializer(many=True)


class ReviewPage(PageSerializer):
    results = ReviewSerializer(many=True)


class ListQuery(StrictSerializer):
    page = serializers.IntegerField(min_value=1, max_value=100000, default=1)


class CandidateQuery(ListQuery):
    decision = serializers.ChoiceField(choices=["pending", "approve", "reject"], required=False)
    quality = serializers.ChoiceField(
        choices=["new", "equivalent", "duplicate", "conflict", "invalid"], required=False
    )
