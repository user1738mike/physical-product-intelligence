from django.db import connection, transaction
from django.db.models import F
from django.http import HttpResponse
from django.urls import path
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.response import Response

from accounts.serializers import StrictSerializer
from accounts.views import PrivateResponseView
from commercial import services as commercial
from compatibility.models import Assessment
from products.models import Product
from products.services import products_in

from . import exports, services
from .models import SCOPES, Admission, Credential, Delivery, Destination, PlanPolicy


class BearerAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer ") or len(header) > 100:
            raise AuthenticationFailed("An integration Authorization header is required.")
        item = services.authenticate(header[7:])
        return item.issuer, item

    def authenticate_header(self, request):
        return "Bearer"


class BearerSchema(OpenApiAuthenticationExtension):
    target_class = BearerAuthentication
    name = "integrationBearer"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "ppi_i_<public-id>.<secret>"}


class CredentialInput(StrictSerializer):
    name = serializers.CharField(max_length=80)
    scopes = serializers.ListField(
        child=serializers.ChoiceField(choices=SCOPES), min_length=1, max_length=3
    )
    expires_at = serializers.DateTimeField()
    rotate = serializers.UUIDField(required=False)
    revoke_old = serializers.BooleanField(default=True)


class CredentialOutput(serializers.ModelSerializer):
    class Meta:
        model = Credential
        fields = [
            "id",
            "name",
            "scopes",
            "issuer_id",
            "created_at",
            "expires_at",
            "revoked_at",
            "last_used_at",
        ]


class RevealCredential(CredentialOutput):
    secret = serializers.CharField()

    class Meta(CredentialOutput.Meta):
        fields = CredentialOutput.Meta.fields + ["secret"]


class DestinationInput(StrictSerializer):
    url = serializers.CharField(max_length=500)
    subscriptions = serializers.ListField(
        child=serializers.ChoiceField(choices=["assessment.completed"]), max_length=1
    )
    enabled = serializers.BooleanField(default=True)
    expected_revision = serializers.IntegerField(min_value=1, required=False)


class DestinationOutput(serializers.ModelSerializer):
    class Meta:
        model = Destination
        fields = [
            "id",
            "url",
            "revision",
            "enabled",
            "subscriptions",
            "key_version",
            "overlap_until",
        ]


class RevealDestination(DestinationOutput):
    secret = serializers.CharField(allow_null=True)

    class Meta(DestinationOutput.Meta):
        fields = DestinationOutput.Meta.fields + ["secret"]


class DeliveryOutput(serializers.ModelSerializer):
    class Meta:
        model = Delivery
        fields = [
            "id",
            "event_id",
            "destination_id",
            "revision",
            "state",
            "attempts",
            "due_at",
            "expires_at",
            "diagnostic",
            "status_code",
            "replays",
        ]


class ManagementOutput(serializers.Serializer):
    outbound_available = serializers.BooleanField()
    credential_creation_available = serializers.BooleanField()
    allowances = serializers.DictField(child=serializers.IntegerField())
    credentials = CredentialOutput(many=True)
    destinations = DestinationOutput(many=True)
    deliveries = DeliveryOutput(many=True)


class Management(PrivateResponseView):
    @extend_schema(responses=ManagementOutput)
    @transaction.atomic
    def get(self, request, organization_id):
        org, _ = services.management(request.user, organization_id)
        assignment = commercial.current(org)
        policy = (
            PlanPolicy.objects.filter(plan=assignment.plan).first()
            if assignment and assignment.status == "active" and org.is_active
            else None
        )
        return Response(
            {
                "outbound_available": bool(
                    services.available() and policy and policy.webhooks_enabled
                ),
                "credential_creation_available": bool(policy and policy.api_enabled),
                "allowances": {
                    "credentials": policy.credentials_limit if policy else 0,
                    "destinations": policy.destinations_limit if policy else 0,
                },
                "credentials": CredentialOutput(
                    Credential.objects.filter(organization=org).order_by(
                        F("revoked_at").asc(nulls_first=True), "-expires_at", "-created_at"
                    )[:100],
                    many=True,
                ).data,
                "destinations": DestinationOutput(
                    Destination.objects.filter(organization=org).order_by(
                        "-enabled", "-created_at"
                    )[:100],
                    many=True,
                ).data,
                "deliveries": DeliveryOutput(
                    Delivery.objects.filter(event__organization=org).order_by(
                        "-event__created_at", "id"
                    )[:100],
                    many=True,
                ).data,
            }
        )


class Credentials(PrivateResponseView):
    @extend_schema(request=CredentialInput, responses={201: RevealCredential})
    def post(self, request, organization_id):
        value = CredentialInput(data=request.data)
        value.is_valid(raise_exception=True)
        item, secret = services.create_credential(
            request.user, organization_id, **value.validated_data
        )
        return Response({**CredentialOutput(item).data, "secret": secret}, status=201)


class Revoke(PrivateResponseView):
    @extend_schema(request=None, responses=CredentialOutput)
    def post(self, request, organization_id, credential_id):
        return Response(
            CredentialOutput(services.revoke(request.user, organization_id, credential_id)).data
        )


class Destinations(PrivateResponseView):
    @extend_schema(request=DestinationInput, responses={201: RevealDestination})
    def post(self, request, organization_id):
        value = DestinationInput(data=request.data)
        value.is_valid(raise_exception=True)
        item, secret = services.configure_destination(
            request.user, organization_id, **value.validated_data
        )
        return Response({**DestinationOutput(item).data, "secret": secret}, status=201)


class DestinationDetail(PrivateResponseView):
    @extend_schema(request=DestinationInput, responses=DestinationOutput)
    def patch(self, request, organization_id, destination_id):
        value = DestinationInput(data=request.data)
        value.is_valid(raise_exception=True)
        item, _ = services.configure_destination(
            request.user, organization_id, destination_id=destination_id, **value.validated_data
        )
        return Response(DestinationOutput(item).data)


class RotationInput(StrictSerializer):
    immediate = serializers.BooleanField(default=False)


class SigningRotation(PrivateResponseView):
    @extend_schema(request=RotationInput, responses=RevealDestination)
    def post(self, request, organization_id, destination_id):
        value = RotationInput(data=request.data)
        value.is_valid(raise_exception=True)
        item, secret = services.rotate_signing(
            request.user, organization_id, destination_id, **value.validated_data
        )
        return Response({**DestinationOutput(item).data, "secret": secret})


class Replay(PrivateResponseView):
    @extend_schema(request=None, responses=DeliveryOutput)
    def post(self, request, organization_id, delivery_id):
        return Response(
            DeliveryOutput(services.replay(request.user, organization_id, delivery_id)).data
        )


class ReadQuery(StrictSerializer):
    after = serializers.UUIDField(required=False)
    limit = serializers.IntegerField(min_value=1, max_value=25, default=25)
    search = serializers.CharField(max_length=80, required=False)
    overall = serializers.ChoiceField(
        choices=["compatible", "incompatible", "indeterminate"], required=False
    )


class IntegrationRead(PrivateResponseView):
    authentication_classes = [BearerAuthentication]
    required_scope = "catalog:read"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if self.required_scope not in request.auth.scopes:
            raise PermissionDenied("Credential scope does not permit this read.")
        self.admission = services.admit(request.auth)

    def finalize_response(self, request, response, *args, **kwargs):
        try:
            return super().finalize_response(request, response, *args, **kwargs)
        finally:
            if getattr(self, "admission", None):
                Admission.objects.filter(pk=self.admission.pk).delete()

    def bounded(self, value):
        return HttpResponse(exports.bounded_json(value), content_type="application/json")

    @transaction.atomic
    def page(self, request, query, serialize):
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '3s'")
        params = ReadQuery(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        data = params.validated_data
        if "search" in data:
            if query.model is not Product:
                raise ValidationError("Search is only supported for catalog reads.")
            query = query.filter(sku__icontains=data["search"])
        if "overall" in data:
            if query.model is not Assessment:
                raise ValidationError("Outcome is only supported for assessments.")
            query = query.filter(overall=data["overall"])
        if data.get("after"):
            query = query.filter(pk__gt=data["after"])
        rows = list(query.order_by("pk")[: data["limit"] + 1])
        return self.bounded(
            {
                "schema_version": "1",
                "results": [serialize(item) for item in rows[: data["limit"]]],
                "next_after": str(rows[data["limit"] - 1].pk)
                if len(rows) > data["limit"]
                else None,
            }
        )


def product_data(item):
    return {
        "id": str(item.pk),
        "sku": item.sku,
        "name": item.name,
        "is_active": item.is_active,
        "revision": item.latest_revision_number,
    }


class Products(IntegrationRead):
    @extend_schema(
        operation_id="integration_catalog_list",
        responses=OpenApiTypes.OBJECT,
        parameters=[ReadQuery],
    )
    def get(self, request):
        return self.page(request, products_in(request.auth.organization), product_data)


class ProductDetail(IntegrationRead):
    @extend_schema(operation_id="integration_catalog_detail", responses=OpenApiTypes.OBJECT)
    @transaction.atomic
    def get(self, request, product_id):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '3s'")
            return self.bounded(
                product_data(products_in(request.auth.organization).get(pk=product_id))
            )
        except Product.DoesNotExist:
            raise NotFound("Product not found.") from None


class Assessments(IntegrationRead):
    required_scope = "assessments:read"

    @extend_schema(
        operation_id="integration_assessment_list",
        responses=OpenApiTypes.OBJECT,
        parameters=[ReadQuery],
    )
    def get(self, request):
        return self.page(
            request,
            Assessment.objects.filter(organization=request.auth.organization),
            lambda item: {
                "id": str(item.pk),
                "created_at": item.created_at.isoformat(),
                "overall": item.overall,
                "product_id": str(item.product_id),
            },
        )


class AssessmentDetail(IntegrationRead):
    required_scope = "assessments:read"

    def item(self, request, assessment_id):
        try:
            from compatibility.services import assessment_get

            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '3s'")
                return assessment_get(request.auth.organization, assessment_id)
        except Assessment.DoesNotExist:
            raise NotFound("Assessment not found.") from None

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, assessment_id):
        return self.bounded(exports.project(self.item(request, assessment_id)))


class AssessmentExport(AssessmentDetail):
    required_scope = "assessments:export"

    @extend_schema(
        responses={
            (200, "application/json"): OpenApiTypes.OBJECT,
            (200, "text/csv"): OpenApiTypes.STR,
        }
    )
    def get(self, request, assessment_id, export_format):
        if export_format not in {"json", "csv"}:
            raise NotFound()
        body, content = exports.export(self.item(request, assessment_id), export_format)
        response = HttpResponse(body, content_type=content)
        response["Content-Disposition"] = (
            f'attachment; filename="assessment-{assessment_id}.{export_format}"'
        )
        return response


management_urls = [
    path("", Management.as_view()),
    path("credentials/", Credentials.as_view()),
    path("credentials/<uuid:credential_id>/revoke/", Revoke.as_view()),
    path("destinations/", Destinations.as_view()),
    path("destinations/<uuid:destination_id>/", DestinationDetail.as_view()),
    path("destinations/<uuid:destination_id>/rotate/", SigningRotation.as_view()),
    path("deliveries/<uuid:delivery_id>/replay/", Replay.as_view()),
]
urlpatterns = [
    path("products/", Products.as_view()),
    path("products/<uuid:product_id>/", ProductDetail.as_view()),
    path("assessments/", Assessments.as_view()),
    path("assessments/<uuid:assessment_id>/", AssessmentDetail.as_view()),
    path(
        "assessments/<uuid:assessment_id>/export/<str:export_format>/", AssessmentExport.as_view()
    ),
]
