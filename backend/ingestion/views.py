import json

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from accounts.views import PrivateResponseView
from operations.throttling import SharedRateThrottle
from organizations.services import authorize
from organizations.views import page
from products.services import validated

from . import services
from .models import Candidate, ImportJob
from .serializers import (
    CandidatePage,
    CandidateQuery,
    CandidateSerializer,
    CreationInput,
    DecisionInput,
    JobPage,
    JobSerializer,
    ListQuery,
    MappingInput,
    OptionsInput,
    ReviewPage,
    ReviewSerializer,
    RowPage,
    RowSerializer,
    UploadInput,
    VersionInput,
)
from .storage import read_upload


class LimitsSerializer(serializers.Serializer):
    formats = serializers.ListField(child=serializers.CharField())
    limits = serializers.DictField(child=serializers.IntegerField())
    fields = serializers.ListField(child=serializers.CharField())


class LimitsView(PrivateResponseView):
    @extend_schema(responses=LimitsSerializer)
    def get(self, request, organization_id):
        authorize(request.user, organization_id)
        from .serializers import FIELDS

        return Response(
            {
                "formats": ["csv", "xlsx", "pdf", "txt"],
                "limits": settings.INGESTION_LIMITS,
                "fields": FIELDS,
            }
        )


class JobsView(PrivateResponseView):
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [SharedRateThrottle]
    throttle_scope = "imports"

    @extend_schema(operation_id="import_jobs_list", responses=JobPage, parameters=[ListQuery])
    def get(self, request, organization_id):
        org, _ = authorize(request.user, organization_id)
        validated(ListQuery, request.query_params.dict())
        return page(request, ImportJob.objects.filter(organization=org), JobSerializer)

    @extend_schema(request=UploadInput, responses={201: JobSerializer})
    def post(self, request, organization_id):
        # Resolve authority before accessing/parsing an untrusted multipart body.
        authorize(request.user, organization_id)
        payload = request.data
        if getattr(request._request, "ingestion_oversized", False):
            raise serializers.ValidationError("Upload exceeds the configured byte limit.")
        values = validated(UploadInput, payload)
        job = services.upload(request.user, organization_id, values["file"])
        return Response(JobSerializer(job).data, status=201)


class JobView(PrivateResponseView):
    @extend_schema(responses=JobSerializer)
    def get(self, request, organization_id, job_id):
        return Response(JobSerializer(services.job_in(request.user, organization_id, job_id)).data)


class ActionView(PrivateResponseView):
    action = ""
    input_class = VersionInput
    throttle_classes = [SharedRateThrottle]
    throttle_scope = "imports"

    @extend_schema(request=VersionInput, responses=JobSerializer)
    def post(self, request, organization_id, job_id):
        values = validated(self.input_class, request.data)
        result = getattr(services, self.action)(request.user, organization_id, job_id, values)
        return Response(JobSerializer(result).data)


class ValidateView(ActionView):
    action, input_class = "validate", OptionsInput

    @extend_schema(request=OptionsInput, responses=JobSerializer)
    def post(self, *args, **kwargs):
        return super().post(*args, **kwargs)


class MappingView(ActionView):
    action, input_class = "map_fields", MappingInput

    @extend_schema(request=MappingInput, responses=JobSerializer)
    def post(self, *args, **kwargs):
        return super().post(*args, **kwargs)


class ProcessView(ActionView):
    action = "process"


class ApplyView(ActionView):
    action = "apply"


class CancelView(ActionView):
    action = "cancel"


class RefreshView(ActionView):
    action = "refresh"


class RowsView(PrivateResponseView):
    @extend_schema(responses=RowPage, parameters=[ListQuery])
    def get(self, request, organization_id, job_id):
        job = services.job_in(request.user, organization_id, job_id)
        validated(ListQuery, request.query_params.dict())
        return page(request, job.rows.all(), RowSerializer)


class CreationView(PrivateResponseView):
    @extend_schema(request=CreationInput, responses=RowSerializer)
    def post(self, request, organization_id, job_id, row_id):
        result = services.approve_creation(
            request.user, organization_id, job_id, row_id, validated(CreationInput, request.data)
        )
        return Response(RowSerializer(result).data)


class CandidatesView(PrivateResponseView):
    @extend_schema(responses=CandidatePage, parameters=[CandidateQuery])
    def get(self, request, organization_id, job_id):
        job = services.job_in(request.user, organization_id, job_id)
        values = validated(CandidateQuery, request.query_params.dict())
        values.pop("page", None)
        query = Candidate.objects.filter(row__job=job, **values).select_related("row")
        return page(request, query, CandidateSerializer)


class DecisionView(PrivateResponseView):
    @extend_schema(request=DecisionInput, responses=CandidateSerializer)
    def post(self, request, organization_id, job_id, candidate_id):
        candidate = services.review(
            request.user,
            organization_id,
            job_id,
            candidate_id,
            validated(DecisionInput, request.data),
        )
        return Response(CandidateSerializer(candidate).data)


class HistoryView(PrivateResponseView):
    @extend_schema(responses=ReviewPage, parameters=[ListQuery])
    def get(self, request, organization_id, job_id):
        job = services.job_in(request.user, organization_id, job_id)
        validated(ListQuery, request.query_params.dict())
        return page(request, job.reviews.all(), ReviewSerializer)


class FileView(PrivateResponseView):
    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request, organization_id, job_id):
        job = services.job_in(request.user, organization_id, job_id)
        response = HttpResponse(read_upload(job), content_type="application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="source-{job.pk}.{job.format}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response


class ErrorsView(PrivateResponseView):
    @extend_schema(responses={(200, "application/json"): dict})
    def get(self, request, organization_id, job_id):
        job = services.job_in(request.user, organization_id, job_id)
        data = {
            "job_id": str(job.pk),
            "errors": job.errors,
            "rows": [
                {
                    "number": row.number,
                    "location": row.location,
                    "errors": row.errors,
                    "candidates": [
                        {"field": c.field, "errors": c.errors, "decision": c.decision}
                        for c in row.candidates.all()
                        if c.errors or c.decision == "reject"
                    ],
                }
                for row in job.rows.prefetch_related("candidates").all()
            ],
        }
        response = HttpResponse(json.dumps(data), content_type="application/json")
        response["Content-Disposition"] = f'attachment; filename="errors-{job.pk}.json"'
        return response
