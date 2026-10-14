from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from accounts.views import PrivateResponseView
from organizations.services import authorize
from organizations.views import page

from . import services
from .serializers import (
    EvidenceInput,
    EvidencePage,
    EvidenceSerializer,
    PackagingPage,
    PackagingSerializer,
    ProductCreateInput,
    ProductPage,
    ProductSerializer,
    ProductStateInput,
    RevisionInput,
    RevisionPage,
    RevisionSerializer,
)


def scoped_product(request, organization_id, product_id):
    organization, _ = authorize(request.user, organization_id)
    return services.product_in(organization, product_id)


class ProductsView(PrivateResponseView):
    @extend_schema(operation_id="products_list", responses=ProductPage)
    def get(self, request, organization_id):
        organization, _ = authorize(request.user, organization_id)
        return page(request, services.products_in(organization), ProductSerializer)

    @extend_schema(request=ProductCreateInput, responses={201: ProductSerializer})
    def post(self, request, organization_id):
        product = services.create_product(request.user, organization_id, request.data)
        return Response(ProductSerializer(product).data, status=201)


class ProductDetailView(PrivateResponseView):
    @extend_schema(responses=ProductSerializer)
    def get(self, request, organization_id, product_id):
        product = scoped_product(request, organization_id, product_id)
        product = services.products_in(product.organization).get(pk=product.pk)
        return Response(ProductSerializer(product).data)


class ProductStateView(PrivateResponseView):
    @extend_schema(request=ProductStateInput, responses=ProductSerializer)
    def post(self, request, organization_id, product_id):
        product = services.set_product_active(
            request.user, organization_id, product_id, request.data
        )
        return Response(ProductSerializer(product).data)


class RevisionsView(PrivateResponseView):
    @extend_schema(operation_id="product_revisions_list", responses=RevisionPage)
    def get(self, request, organization_id, product_id):
        product = scoped_product(request, organization_id, product_id)
        return page(request, services.revisions_in(product), RevisionSerializer)

    @extend_schema(request=RevisionInput, responses={201: RevisionSerializer})
    def post(self, request, organization_id, product_id):
        revision = services.create_revision(request.user, organization_id, product_id, request.data)
        return Response(RevisionSerializer(revision).data, status=201)


class RevisionDetailView(PrivateResponseView):
    @extend_schema(responses=RevisionSerializer)
    def get(self, request, organization_id, product_id, revision_id):
        product = scoped_product(request, organization_id, product_id)
        return Response(RevisionSerializer(services.revision_in(product, revision_id)).data)


class EvidenceView(PrivateResponseView):
    @extend_schema(operation_id="product_evidence_list", responses=EvidencePage)
    def get(self, request, organization_id, product_id):
        product = scoped_product(request, organization_id, product_id)
        return page(request, product.evidence.all(), EvidenceSerializer)

    @extend_schema(request=EvidenceInput, responses={201: EvidenceSerializer})
    def post(self, request, organization_id, product_id):
        evidence = services.create_evidence(request.user, organization_id, product_id, request.data)
        return Response(EvidenceSerializer(evidence).data, status=201)


class EvidenceDetailView(PrivateResponseView):
    @extend_schema(responses=EvidenceSerializer)
    def get(self, request, organization_id, product_id, evidence_id):
        product = scoped_product(request, organization_id, product_id)
        return Response(EvidenceSerializer(services.evidence_in(product, evidence_id)).data)


class PackagingView(PrivateResponseView):
    @extend_schema(operation_id="product_packaging_list", responses=PackagingPage)
    def get(self, request, organization_id, product_id, revision_id):
        product = scoped_product(request, organization_id, product_id)
        revision = services.revision_in(product, revision_id)
        return page(
            request, revision.packaging.prefetch_related("measurements"), PackagingSerializer
        )


class PackagingDetailView(PrivateResponseView):
    @extend_schema(responses=PackagingSerializer)
    def get(self, request, organization_id, product_id, revision_id, packaging_id):
        product = scoped_product(request, organization_id, product_id)
        revision = services.revision_in(product, revision_id)
        try:
            packaging = revision.packaging.prefetch_related("measurements").get(pk=packaging_id)
        except revision.packaging.model.DoesNotExist as error:
            raise NotFound("Packaging profile not found.") from error
        return Response(PackagingSerializer(packaging).data)
