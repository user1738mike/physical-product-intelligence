from django.db import DatabaseError
from django.http import HttpResponse
from django.urls import path
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers import StrictSerializer
from accounts.views import PrivateResponseView
from organizations.services import ADMIN, OWNER, authorize

from . import services
from .models import PaymentOperation, Statement


class CorrectionOutput(serializers.Serializer):
    id = serializers.UUIDField()
    delta_minor = serializers.CharField()
    created_at = serializers.DateTimeField()


class SettlementOutput(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    amount_minor = serializers.CharField()
    created_at = serializers.DateTimeField()


class StatementOutput(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    settlement_status = serializers.CharField()
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    currency = serializers.CharField()
    exponent = serializers.IntegerField()
    total_minor = serializers.CharField()
    original_total_minor = serializers.CharField()
    settled_minor = serializers.CharField()
    remaining_minor = serializers.CharField()
    snapshot = serializers.JSONField()
    mode = serializers.CharField()
    access_fulfilled = serializers.BooleanField()
    download_path = serializers.CharField()
    corrections = CorrectionOutput(many=True)
    settlements = SettlementOutput(many=True)


class OperationOutput(serializers.Serializer):
    id = serializers.UUIDField()
    statement_id = serializers.UUIDField()
    status = serializers.CharField()
    amount_minor = serializers.CharField()
    currency = serializers.CharField()
    expires_at = serializers.DateTimeField()


class BillingOutput(serializers.Serializer):
    collection_available = serializers.BooleanField()
    statements = StatementOutput(many=True)
    operations = OperationOutput(many=True)
    unapplied_credit = serializers.DictField(child=serializers.CharField())


class OperationInput(StrictSerializer):
    statement_id = serializers.UUIDField()
    request_id = serializers.UUIDField()


class ReceiptOutput(serializers.Serializer):
    received = serializers.BooleanField()


class Summary(PrivateResponseView):
    @extend_schema(operation_id="billing_summary", responses=BillingOutput)
    def get(self, request, organization_id):
        return Response(BillingOutput(services.account_summary(request.user, organization_id)).data)


def scoped_statement(actor, org_id, statement_id):
    org, _ = authorize(actor, org_id, roles={OWNER, ADMIN}, allow_suspended=True)
    try:
        return Statement.objects.select_related("account", "price").get(
            account__organization=org, pk=statement_id
        )
    except Statement.DoesNotExist:
        from rest_framework.exceptions import NotFound

        raise NotFound("Statement not found.") from None


class Detail(PrivateResponseView):
    @extend_schema(operation_id="billing_statement", responses=StatementOutput)
    def get(self, request, organization_id, statement_id):
        return Response(
            StatementOutput(
                services.statement_data(
                    scoped_statement(request.user, organization_id, statement_id)
                )
            ).data
        )


class Download(PrivateResponseView):
    @extend_schema(
        operation_id="billing_statement_download",
        responses={(200, "text/plain"): OpenApiTypes.STR},
    )
    def get(self, request, organization_id, statement_id):
        item = scoped_statement(request.user, organization_id, statement_id)
        value = services.statement_data(item)
        body = (
            "Internal billing statement — not a tax invoice\n"
            + "\n".join(
                f"{key}: {value[key]}"
                for key in (
                    "id",
                    "status",
                    "currency",
                    "exponent",
                    "total_minor",
                    "settled_minor",
                    "remaining_minor",
                    "period_start",
                    "period_end",
                )
            )
            + "\n"
        )
        response = HttpResponse(body, content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="statement-{item.pk}.txt"'
        return response


class Operations(PrivateResponseView):
    @extend_schema(
        operation_id="billing_operation_request",
        request=OperationInput,
        responses={201: OperationOutput},
    )
    def post(self, request, organization_id):
        data = OperationInput(data=request.data)
        data.is_valid(raise_exception=True)
        item = services.request_operation(request.user, organization_id, **data.validated_data)
        return Response(
            OperationOutput(
                {
                    "id": item.pk,
                    "statement_id": item.statement_id,
                    "status": item.state,
                    "amount_minor": str(item.amount_minor),
                    "currency": item.currency,
                    "expires_at": item.expires_at,
                }
            ).data,
            status=201,
        )


class SyntheticInbox(APIView):
    # Only this test ingress omits sessions/CSRF. Real adapters require their own official verifier.
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="billing_synthetic_inbox", request=None, responses={202: ReceiptOutput}
    )
    def post(self, request):
        if int(request.META.get("CONTENT_LENGTH") or 0) > 65536:
            return Response({"detail": "Delivery exceeds size limit."}, status=413)
        try:
            services.receive(
                request.body,
                request.headers.get("X-PPI-Test-Time"),
                request.headers.get("X-PPI-Test-Proof"),
            )
        except DatabaseError:
            return Response({"detail": "Event storage is unavailable; retry delivery."}, status=503)
        return Response({"received": True}, status=202)


class OperationDetail(PrivateResponseView):
    @extend_schema(operation_id="billing_operation_status", responses=OperationOutput)
    def get(self, request, organization_id, operation_id):
        org, _ = authorize(
            request.user, organization_id, roles={OWNER, ADMIN}, allow_suspended=True
        )
        try:
            item = PaymentOperation.objects.get(account__organization=org, pk=operation_id)
        except PaymentOperation.DoesNotExist:
            from rest_framework.exceptions import NotFound

            raise NotFound("Operation not found.") from None
        return Response(
            OperationOutput(
                {
                    "id": item.pk,
                    "statement_id": item.statement_id,
                    "status": item.state,
                    "amount_minor": str(item.amount_minor),
                    "currency": item.currency,
                    "expires_at": item.expires_at,
                }
            ).data
        )


urlpatterns = [
    path("", Summary.as_view()),
    path("statements/<uuid:statement_id>/", Detail.as_view()),
    path("statements/<uuid:statement_id>/download/", Download.as_view()),
    path("operations/", Operations.as_view()),
    path("operations/<uuid:operation_id>/", OperationDetail.as_view()),
]
