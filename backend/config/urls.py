from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView
from integrations.views import management_urls

from accounts.views import CsrfView, LoginView, LogoutView, MeView, RegisterView
from billing.views import SyntheticInbox
from operations.views import LiveView, ReadyView
from organizations.views import (
    AuditView,
    MemberDetailView,
    MembersView,
    MyMembershipsView,
    OrganizationDetailView,
    OrganizationStateView,
    OrganizationsView,
    TransferView,
)

urlpatterns = [
    path("api/v1/integration/", include("integrations.views")),
    path("api/v1/organizations/<uuid:organization_id>/integrations/", include(management_urls)),
    path("api/v1/billing/synthetic-inbox/", SyntheticInbox.as_view()),
    path("api/v1/organizations/<uuid:organization_id>/billing/", include("billing.views")),
    path("api/v1/organizations/<uuid:organization_id>/commercial/", include("commercial.views")),
    path("api/v1/organizations/<uuid:organization_id>/", include("compatibility.urls")),
    path("api/v1/organizations/<uuid:organization_id>/imports/", include("ingestion.urls")),
    path("api/v1/organizations/<uuid:organization_id>/products/", include("products.urls")),
    path("admin/", admin.site.urls),
    path("api/v1/auth/csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("api/v1/auth/register/", RegisterView.as_view(), name="auth-register"),
    path("api/v1/auth/login/", LoginView.as_view(), name="auth-login"),
    path("api/v1/auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("api/v1/auth/me/", MeView.as_view(), name="auth-me"),
    path("api/v1/auth/memberships/", MyMembershipsView.as_view(), name="my-memberships"),
    path("api/v1/organizations/", OrganizationsView.as_view(), name="organizations"),
    path(
        "api/v1/organizations/<uuid:organization_id>/",
        OrganizationDetailView.as_view(),
        name="organization-detail",
    ),
    path(
        "api/v1/organizations/<uuid:organization_id>/state/",
        OrganizationStateView.as_view(),
        name="organization-state",
    ),
    path(
        "api/v1/organizations/<uuid:organization_id>/members/",
        MembersView.as_view(),
        name="organization-members",
    ),
    path(
        "api/v1/organizations/<uuid:organization_id>/members/<uuid:membership_id>/",
        MemberDetailView.as_view(),
        name="member-detail",
    ),
    path(
        "api/v1/organizations/<uuid:organization_id>/transfer/",
        TransferView.as_view(),
        name="organization-transfer",
    ),
    path(
        "api/v1/organizations/<uuid:organization_id>/audit/",
        AuditView.as_view(),
        name="organization-audit",
    ),
    path("api/v1/health/live/", LiveView.as_view(), name="health-live"),
    path("api/v1/health/ready/", ReadyView.as_view(), name="health-ready"),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
]
