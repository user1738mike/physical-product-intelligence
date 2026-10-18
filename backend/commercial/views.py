from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from accounts.views import PrivateResponseView

from .services import summary


class PlanOutput(serializers.Serializer):
    code = serializers.CharField()
    version = serializers.IntegerField()
    name = serializers.CharField()
    features = serializers.DictField(child=serializers.BooleanField())


class MeterOutput(serializers.Serializer):
    definition = serializers.CharField()
    limit = serializers.IntegerField(allow_null=True)
    used = serializers.IntegerField()
    reserved = serializers.IntegerField()
    remaining = serializers.IntegerField(allow_null=True)


class AssignmentOutput(serializers.Serializer):
    id = serializers.UUIDField()
    plan_code = serializers.CharField()
    plan_version = serializers.IntegerField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField()
    source = serializers.CharField()


class CommercialOutput(serializers.Serializer):
    status = serializers.CharField()
    plan = PlanOutput(allow_null=True)
    starts_at = serializers.DateTimeField(allow_null=True)
    ends_at = serializers.DateTimeField(allow_null=True)
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    metering_started_at = serializers.DateTimeField(allow_null=True)
    historical_usage_complete = serializers.BooleanField()
    meters = serializers.DictField(child=MeterOutput())
    history = AssignmentOutput(many=True)


class CommercialView(PrivateResponseView):
    @extend_schema(operation_id="organization_commercial_summary", responses=CommercialOutput)
    def get(self, request, organization_id):
        return Response(CommercialOutput(summary(request.user, organization_id)).data)


urlpatterns = [path("", CommercialView.as_view(), name="commercial-summary")]
