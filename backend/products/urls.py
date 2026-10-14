from django.urls import path

from .views import (
    EvidenceDetailView,
    EvidenceView,
    PackagingDetailView,
    PackagingView,
    ProductDetailView,
    ProductStateView,
    ProductsView,
    RevisionDetailView,
    RevisionsView,
)

urlpatterns = [
    path("", ProductsView.as_view(), name="products"),
    path("<uuid:product_id>/", ProductDetailView.as_view(), name="product-detail"),
    path("<uuid:product_id>/state/", ProductStateView.as_view(), name="product-state"),
    path("<uuid:product_id>/revisions/", RevisionsView.as_view(), name="product-revisions"),
    path(
        "<uuid:product_id>/revisions/<uuid:revision_id>/",
        RevisionDetailView.as_view(),
        name="product-revision",
    ),
    path("<uuid:product_id>/evidence/", EvidenceView.as_view(), name="product-evidence"),
    path(
        "<uuid:product_id>/evidence/<uuid:evidence_id>/",
        EvidenceDetailView.as_view(),
        name="product-evidence-detail",
    ),
    path(
        "<uuid:product_id>/revisions/<uuid:revision_id>/packaging/",
        PackagingView.as_view(),
        name="product-packaging",
    ),
    path(
        "<uuid:product_id>/revisions/<uuid:revision_id>/packaging/<uuid:packaging_id>/",
        PackagingDetailView.as_view(),
        name="product-packaging-detail",
    ),
]
