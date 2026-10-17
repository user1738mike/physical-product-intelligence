from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from accounts.serializers import StrictSerializer
from accounts.views import PrivateResponseView
from operations.throttling import SharedRateThrottle
from organizations.services import authorize
from products.services import validated

from . import retention, services
from .models import SourceRemoval


class PolicyInput(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=0)
    minimum_days = serializers.IntegerField(min_value=1, max_value=36500, allow_null=True)
    legal_hold = serializers.BooleanField()
    reason = serializers.CharField(max_length=1000, min_length=5)


class PolicyOutput(serializers.Serializer):
    version = serializers.IntegerField()
    minimum_days = serializers.IntegerField(allow_null=True)
    legal_hold = serializers.BooleanField()


class PolicyView(PrivateResponseView):
    throttle_classes = [SharedRateThrottle]
    throttle_scope = "imports"

    @extend_schema(responses=PolicyOutput)
    def get(self, request, organization_id):
        org, _ = authorize(request.user, organization_id)
        return Response(retention.policy_data(org))

    @extend_schema(request=PolicyInput, responses=PolicyOutput)
    def put(self, request, organization_id):
        return Response(
            retention.set_policy(
                request.user, organization_id, **validated(PolicyInput, request.data)
            )
        )


class RemovalInput(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=1000, min_length=5)


class RemovalOutput(serializers.ModelSerializer):
    class Meta:
        model = SourceRemoval
        fields = ["id", "state", "created_at", "claimed_at", "finished_at", "reason", "sha256"]
        read_only_fields = fields


class RemovalView(PrivateResponseView):
    throttle_classes = [SharedRateThrottle]
    throttle_scope = "imports"

    @extend_schema(responses=RemovalOutput(many=True))
    def get(self, request, organization_id, job_id):
        job = services.job_in(request.user, organization_id, job_id)
        return Response(RemovalOutput(job.removals.order_by("-created_at")[:20], many=True).data)

    @extend_schema(request=RemovalInput, responses={202: RemovalOutput})
    def post(self, request, organization_id, job_id):
        value = retention.request_removal(
            request.user, organization_id, job_id, **validated(RemovalInput, request.data)
        )
        return Response(RemovalOutput(value).data, status=202)
