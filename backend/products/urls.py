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
from .workflow_views import (
    AttributeStatesView,
    ClaimDetailView,
    ClaimsView,
    ConfigurationDetailView,
    ConfigurationEvidenceView,
    ConfigurationRevisionsView,
    ConfigurationStateView,
    ConfigurationsView,
    HistoryView,
    PackagingClaimsView,
    SelectionView,
    VerificationView,
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

urlpatterns += [
    path(
        "<uuid:product_id>/packaging/<uuid:packaging_id>/evidence/",
        ConfigurationEvidenceView.as_view(),
    ),
    path("<uuid:product_id>/packaging/", ConfigurationsView.as_view()),
    path("<uuid:product_id>/packaging/<uuid:packaging_id>/", ConfigurationDetailView.as_view()),
    path(
        "<uuid:product_id>/packaging/<uuid:packaging_id>/state/", ConfigurationStateView.as_view()
    ),
    path(
        "<uuid:product_id>/packaging/<uuid:packaging_id>/revisions/",
        ConfigurationRevisionsView.as_view(),
    ),
]
for prefix, collection_view in [
    ("<uuid:product_id>/", ClaimsView),
    ("<uuid:product_id>/packaging/<uuid:packaging_id>/", PackagingClaimsView),
]:
    urlpatterns += [
        path(prefix + "claims/", collection_view.as_view()),
        path(prefix + "claims/<uuid:claim_id>/", ClaimDetailView.as_view()),
        path(prefix + "claims/<uuid:claim_id>/verification/", VerificationView.as_view()),
        path(prefix + "attributes/", AttributeStatesView.as_view()),
        path(prefix + "attributes/<str:attribute>/selection/", SelectionView.as_view()),
        path(prefix + "history/", HistoryView.as_view()),
    ]
