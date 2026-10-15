from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from accounts.serializers import StrictSerializer
from accounts.views import PrivateResponseView
from organizations.services import authorize
from organizations.views import page
from products.services import validated

from . import services
from .models import Assessment
from .serializers import (
    ActivationInput,
    AssessmentInput,
    AssessmentPage,
    AssessmentQuery,
    AssessmentSerializer,
    AssessmentSummary,
    EquipmentEdit,
    EquipmentInput,
    EquipmentPage,
    EquipmentQuery,
    EquipmentRevisionPage,
    EquipmentRevisionSerializer,
    EquipmentSerializer,
    EquipmentState,
    PageQuery,
    RuleSetInput,
    RuleSetPage,
    RuleSetSerializer,
)


def scope(request, org_id, equipment_id):
    org, _ = authorize(request.user, org_id)
    return services.equipment_get(org, equipment_id)


class EquipmentList(PrivateResponseView):
    @extend_schema(
        operation_id="equipment_list", parameters=[EquipmentQuery], responses=EquipmentPage
    )
    def get(self, request, organization_id):
        org, _ = authorize(request.user, organization_id)
        values = validated(EquipmentQuery, request.query_params.dict())
        query = services.equipment_in(org)
        if values["search"]:
            query = query.filter(
                Q(code__icontains=values["search"])
                | Q(definition__name__icontains=values["search"])
            )
        if "status" in values:
            query = query.filter(status=values["status"])
        if "category" in values:
            query = query.filter(definition__category=values["category"])
        return page(request, query, EquipmentSerializer)

    @extend_schema(request=EquipmentInput, responses={201: EquipmentSerializer})
    def post(self, request, organization_id):
        return Response(
            EquipmentSerializer(
                services.create_equipment(request.user, organization_id, request.data)
            ).data,
            status=201,
        )


class EquipmentDetail(PrivateResponseView):
    @extend_schema(responses=EquipmentSerializer)
    def get(self, request, organization_id, equipment_id):
        return Response(EquipmentSerializer(scope(request, organization_id, equipment_id)).data)

    @extend_schema(request=EquipmentEdit, responses=EquipmentSerializer)
    def patch(self, request, organization_id, equipment_id):
        return Response(
            EquipmentSerializer(
                services.edit_equipment(request.user, organization_id, equipment_id, request.data)
            ).data
        )


class StateView(PrivateResponseView):
    @extend_schema(request=EquipmentState, responses=EquipmentSerializer)
    def post(self, request, organization_id, equipment_id):
        return Response(
            EquipmentSerializer(
                services.equipment_state(request.user, organization_id, equipment_id, request.data)
            ).data
        )


class RevisionsView(PrivateResponseView):
    @extend_schema(
        operation_id="equipment_revision_history",
        parameters=[PageQuery],
        responses=EquipmentRevisionPage,
    )
    def get(self, request, organization_id, equipment_id):
        equipment = scope(request, organization_id, equipment_id)
        validated(PageQuery, request.query_params.dict())
        return page(request, equipment.revisions.all(), EquipmentRevisionSerializer)


class RulesView(PrivateResponseView):
    @extend_schema(
        operation_id="equipment_rule_sets", parameters=[PageQuery], responses=RuleSetPage
    )
    def get(self, request, organization_id, equipment_id):
        equipment = scope(request, organization_id, equipment_id)
        validated(PageQuery, request.query_params.dict())
        return page(request, equipment.rule_sets.select_related("activation"), RuleSetSerializer)

    @extend_schema(request=RuleSetInput, responses={201: RuleSetSerializer})
    def post(self, request, organization_id, equipment_id):
        result = services.create_rules(request.user, organization_id, equipment_id, request.data)
        return Response(RuleSetSerializer(result).data, status=201)


class RuleDetail(PrivateResponseView):
    @extend_schema(responses=RuleSetSerializer)
    def get(self, request, organization_id, equipment_id, rule_id):
        equipment = scope(request, organization_id, equipment_id)
        return Response(RuleSetSerializer(services.rule_get(equipment, rule_id)).data)


class ActivateView(PrivateResponseView):
    @extend_schema(request=ActivationInput, responses=RuleSetSerializer)
    def post(self, request, organization_id, equipment_id, rule_id):
        result = services.activate(
            request.user, organization_id, equipment_id, rule_id, request.data
        )
        return Response(RuleSetSerializer(result).data)


class AssessmentsView(PrivateResponseView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "assessments"

    @extend_schema(
        operation_id="assessment_history", parameters=[AssessmentQuery], responses=AssessmentPage
    )
    def get(self, request, organization_id):
        org, _ = authorize(request.user, organization_id)
        values = validated(AssessmentQuery, request.query_params.dict())
        query = Assessment.objects.filter(organization=org).defer(
            "inputs", "equipment_snapshot", "rule_snapshot", "results"
        )
        for key in ("product_id", "equipment_id", "overall"):
            if key in values:
                query = query.filter(**{key: values[key]})
        if "date_from" in values:
            query = query.filter(created_at__gte=values["date_from"])
        if "date_to" in values:
            query = query.filter(created_at__lte=values["date_to"])
        return page(request, query, AssessmentSummary)

    @extend_schema(request=AssessmentInput, responses={201: AssessmentSerializer})
    def post(self, request, organization_id):
        result = services.assess(request.user, organization_id, request.data)
        return Response(AssessmentSerializer(result).data, status=201)


class AssessmentDetail(PrivateResponseView):
    @extend_schema(responses=AssessmentSerializer)
    def get(self, request, organization_id, assessment_id):
        org, _ = authorize(request.user, organization_id)
        return Response(AssessmentSerializer(services.assessment_get(org, assessment_id)).data)


class CompareQuery(StrictSerializer):
    other_id = serializers.UUIDField()


class ComparisonSerializer(serializers.Serializer):
    first_id = serializers.UUIDField()
    second_id = serializers.UUIDField()
    first_result = serializers.CharField()
    second_result = serializers.CharField()
    changes = serializers.ListField(child=serializers.DictField())


class CompareView(PrivateResponseView):
    @extend_schema(parameters=[CompareQuery], responses=ComparisonSerializer)
    def get(self, request, organization_id, assessment_id):
        org, _ = authorize(request.user, organization_id)
        values = validated(CompareQuery, request.query_params.dict())
        return Response(services.compare(org, assessment_id, values["other_id"]))
