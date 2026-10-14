from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from accounts.serializers import StrictSerializer
from accounts.views import PrivateResponseView
from organizations.serializers import AuditPageSerializer, AuditSerializer
from organizations.views import page

from . import services, workflows
from .models import Evidence
from .serializers import EvidencePage, EvidenceSerializer
from .views import scoped_product
from .workflow_serializers import (
    AttributeStatesSerializer,
    ClaimInput,
    ClaimPage,
    ClaimSerializer,
    ConfigurationEditInput,
    ConfigurationInput,
    ConfigurationPage,
    ConfigurationRevisionPage,
    ConfigurationRevisionSerializer,
    ConfigurationSerializer,
    ConfigurationStateInput,
    SelectionInput,
    SelectionSerializer,
    VerificationInput,
)


class PageQuery(StrictSerializer):
    page = serializers.IntegerField(min_value=1, max_value=100000, required=False, default=1)


def scope(request, organization_id, product_id, packaging_id=None):
    product = scoped_product(request, organization_id, product_id)
    packaging = workflows.configuration_in(product, packaging_id) if packaging_id else None
    return product, packaging


def paginated(request, query, serializer):
    services.validated(PageQuery, request.query_params.dict())
    return page(request, query, serializer)


class ConfigurationsView(PrivateResponseView):
    @extend_schema(operation_id="packaging_configurations_list", responses=ConfigurationPage)
    def get(self, request, organization_id, product_id):
        product, _ = scope(request, organization_id, product_id)
        return paginated(request, product.configurations.all(), ConfigurationSerializer)

    @extend_schema(request=ConfigurationInput, responses={201: ConfigurationSerializer})
    def post(self, request, organization_id, product_id):
        item = workflows.create_configuration(
            request.user, organization_id, product_id, request.data
        )
        return Response(ConfigurationSerializer(item).data, status=201)


class ConfigurationDetailView(PrivateResponseView):
    @extend_schema(responses=ConfigurationSerializer)
    def get(self, request, organization_id, product_id, packaging_id):
        _, item = scope(request, organization_id, product_id, packaging_id)
        return Response(ConfigurationSerializer(item).data)

    @extend_schema(request=ConfigurationEditInput, responses=ConfigurationSerializer)
    def patch(self, request, organization_id, product_id, packaging_id):
        item = workflows.edit_configuration(
            request.user, organization_id, product_id, packaging_id, request.data
        )
        return Response(ConfigurationSerializer(item).data)


class ConfigurationStateView(PrivateResponseView):
    @extend_schema(request=ConfigurationStateInput, responses=ConfigurationSerializer)
    def post(self, request, organization_id, product_id, packaging_id):
        item = workflows.configuration_state(
            request.user, organization_id, product_id, packaging_id, request.data
        )
        return Response(ConfigurationSerializer(item).data)


class ConfigurationRevisionsView(PrivateResponseView):
    @extend_schema(operation_id="configuration_revisions_list", responses=ConfigurationRevisionPage)
    def get(self, request, organization_id, product_id, packaging_id):
        _, item = scope(request, organization_id, product_id, packaging_id)
        return paginated(request, item.revisions.all(), ConfigurationRevisionSerializer)


class ConfigurationEvidenceView(PrivateResponseView):
    @extend_schema(operation_id="packaging_evidence_sources_list", responses=EvidencePage)
    def get(self, request, organization_id, product_id, packaging_id):
        product, packaging = scope(request, organization_id, product_id, packaging_id)
        query = Evidence.objects.filter(
            product=product, attributeclaim__packaging=packaging
        ).distinct()
        return paginated(request, query, EvidenceSerializer)


class ClaimsView(PrivateResponseView):
    @extend_schema(operation_id="product_attribute_claims_list", responses=ClaimPage)
    def get(self, request, organization_id, product_id, packaging_id=None):
        product, packaging = scope(request, organization_id, product_id, packaging_id)
        return paginated(request, workflows.claims_in(product, packaging), ClaimSerializer)

    @extend_schema(request=ClaimInput, responses={201: ClaimSerializer})
    def post(self, request, organization_id, product_id, packaging_id=None):
        claim = workflows.create_claim(
            request.user, organization_id, product_id, request.data, packaging_id=packaging_id
        )
        return Response(ClaimSerializer(claim).data, status=201)


class PackagingClaimsView(ClaimsView):
    @extend_schema(operation_id="packaging_attribute_claims_list", responses=ClaimPage)
    def get(self, request, organization_id, product_id, packaging_id):
        return super().get(request, organization_id, product_id, packaging_id)


class ClaimDetailView(PrivateResponseView):
    @extend_schema(responses=ClaimSerializer)
    def get(self, request, organization_id, product_id, claim_id, packaging_id=None):
        product, packaging = scope(request, organization_id, product_id, packaging_id)
        return Response(ClaimSerializer(workflows.claim_in(product, packaging, claim_id)).data)


class VerificationView(PrivateResponseView):
    @extend_schema(request=VerificationInput, responses={201: ClaimSerializer})
    def post(self, request, organization_id, product_id, claim_id, packaging_id=None):
        claim = workflows.verify_claim(
            request.user,
            organization_id,
            product_id,
            claim_id,
            request.data,
            packaging_id=packaging_id,
        )
        return Response(ClaimSerializer(claim).data, status=201)


class AttributeStatesView(PrivateResponseView):
    @extend_schema(responses=AttributeStatesSerializer)
    def get(self, request, organization_id, product_id, packaging_id=None):
        product, packaging = scope(request, organization_id, product_id, packaging_id)
        services.validated(PageQuery, request.query_params.dict())
        return Response(
            AttributeStatesSerializer(workflows.attribute_states(product, packaging)).data
        )


class SelectionView(PrivateResponseView):
    @extend_schema(request=SelectionInput, responses={201: SelectionSerializer})
    def post(self, request, organization_id, product_id, attribute, packaging_id=None):
        selection = workflows.select_claim(
            request.user,
            organization_id,
            product_id,
            attribute,
            request.data,
            packaging_id=packaging_id,
        )
        return Response(SelectionSerializer(selection).data, status=201)


class HistoryView(PrivateResponseView):
    @extend_schema(responses=AuditPageSerializer)
    def get(self, request, organization_id, product_id, packaging_id=None):
        product, packaging = scope(request, organization_id, product_id, packaging_id)
        return paginated(request, workflows.history_in(product, packaging), AuditSerializer)
