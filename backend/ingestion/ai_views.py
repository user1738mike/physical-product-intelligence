from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from accounts.serializers import StrictSerializer
from accounts.views import PrivateResponseView
from operations.throttling import SharedRateThrottle
from organizations.services import authorize
from products.services import validated

from . import ai_provider, ai_schema, ai_services, services
from .serializers import CandidateSerializer, JobSerializer, VersionInput


class ExtractionStart(StrictSerializer):
    request_id = serializers.UUIDField()
    product_id = serializers.UUIDField()
    packaging_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class AICapability(serializers.Serializer):
    available = serializers.BooleanField()
    reason = serializers.CharField()
    schema_version = serializers.CharField()
    max_candidates = serializers.IntegerField()
    max_text_chars = serializers.IntegerField()
    privacy_notice = serializers.CharField()


class CapabilitiesView(PrivateResponseView):
    @extend_schema(responses=AICapability)
    def get(self, request, organization_id):
        authorize(request.user, organization_id)
        available, reason = ai_provider.availability()
        return Response(
            {
                "available": available,
                "reason": reason,
                "schema_version": ai_schema.VERSION,
                "max_candidates": ai_schema.MAX_CANDIDATES,
                "max_text_chars": ai_schema.MAX_TEXT,
                "privacy_notice": "Explicit processing sends bounded private source text to the "
                "configured provider. Candidates require human review; approval is not physical "
                "verification. Deterministic assessments remain separate.",
            }
        )


class ExtractionStartView(PrivateResponseView):
    throttle_classes = [SharedRateThrottle]
    throttle_scope = "extractions"

    @extend_schema(request=ExtractionStart, responses={201: JobSerializer})
    def post(self, request, organization_id, job_id):
        result = ai_services.start(
            request.user, organization_id, job_id, validated(ExtractionStart, request.data)
        )
        return Response(JobSerializer(result).data, status=201)


class AIProcessView(PrivateResponseView):
    throttle_classes = [SharedRateThrottle]
    throttle_scope = "extractions"

    @extend_schema(request=VersionInput, responses=JobSerializer)
    def post(self, request, organization_id, job_id):
        result = ai_services.process(
            request.user, organization_id, job_id, validated(VersionInput, request.data)
        )
        return Response(JobSerializer(result).data)


class CandidateDetailView(PrivateResponseView):
    @extend_schema(operation_id="import_candidate_detail", responses=CandidateSerializer)
    def get(self, request, organization_id, job_id, candidate_id):
        job = services.job_in(request.user, organization_id, job_id)
        return Response(CandidateSerializer(services.candidate_in(job, candidate_id)).data)
