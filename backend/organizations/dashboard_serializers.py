from rest_framework import serializers

from accounts.serializers import StrictSerializer

from .models import Membership
from .serializers import OrganizationSerializer


class DashboardQuery(StrictSerializer):
    """The overview has a fixed all-time scope and bounded recent lists."""


class ProductCounts(serializers.Serializer):
    total = serializers.IntegerField(min_value=0)
    active = serializers.IntegerField(min_value=0)
    archived = serializers.IntegerField(min_value=0)


class RecentImport(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()


class ImportCounts(serializers.Serializer):
    total = serializers.IntegerField(min_value=0)
    by_status = serializers.DictField(child=serializers.IntegerField(min_value=0))
    awaiting_review = serializers.IntegerField(min_value=0)
    attention = serializers.IntegerField(min_value=0)
    recent = RecentImport(many=True)


class EquipmentCounts(serializers.Serializer):
    total = serializers.IntegerField(min_value=0)
    draft = serializers.IntegerField(min_value=0)
    active = serializers.IntegerField(min_value=0)
    archived = serializers.IntegerField(min_value=0)
    active_with_activated_rules = serializers.IntegerField(min_value=0)


class RecentAssessment(serializers.Serializer):
    id = serializers.UUIDField()
    product_id = serializers.UUIDField()
    equipment_id = serializers.UUIDField()
    overall = serializers.ChoiceField(choices=["compatible", "incompatible", "indeterminate"])
    summary = serializers.CharField()
    created_at = serializers.DateTimeField()


class AssessmentCounts(serializers.Serializer):
    total = serializers.IntegerField(min_value=0)
    compatible = serializers.IntegerField(min_value=0)
    incompatible = serializers.IntegerField(min_value=0)
    indeterminate = serializers.IntegerField(min_value=0)
    recent = RecentAssessment(many=True)


class DashboardSerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    scope = serializers.ChoiceField(choices=["all_time"])
    organization = OrganizationSerializer()
    role = serializers.ChoiceField(choices=Membership.Role.choices)
    products = ProductCounts()
    imports = ImportCounts()
    equipment = EquipmentCounts()
    assessments = AssessmentCounts()
