"""Read-only, tenant-scoped overview; business mutations retain their own services."""

from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from accounts.views import PrivateResponseView
from compatibility.models import Assessment, Equipment, EquipmentRevision, RuleSet
from ingestion.models import ImportJob
from products.models import Product

from .dashboard_serializers import DashboardQuery, DashboardSerializer
from .services import authorize

RECENT_LIMIT = 5


def overview(actor, organization_id):
    # Exactly the same authority as the underlying business list/history endpoints:
    # all tenant roles may read, suspended organizations may not, expired plans may.
    organization, membership = authorize(actor, organization_id)
    products = Product.objects.filter(organization=organization).aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(is_active=True)),
        archived=Count("id", filter=Q(is_active=False)),
    )
    jobs = ImportJob.objects.filter(organization=organization)
    statuses = {status: 0 for status in ImportJob.Status.values}
    statuses.update(
        {
            row["status"]: row["total"]
            for row in jobs.order_by().values("status").annotate(total=Count("id"))
        }
    )
    imports = {
        "total": sum(statuses.values()),
        "by_status": statuses,
        "awaiting_review": statuses[ImportJob.Status.REVIEW],
        "attention": sum(
            statuses[status]
            for status in [
                ImportJob.Status.REVIEW,
                ImportJob.Status.ERRORS,
                ImportJob.Status.FAILED,
            ]
        ),
        "recent": list(
            jobs.order_by("-created_at", "-id").values(
                "id", "display_name", "status", "created_at"
            )[:RECENT_LIMIT]
        ),
    }
    latest_revision = EquipmentRevision.objects.filter(equipment=OuterRef("pk")).order_by("-number")
    equipment = (
        Equipment.objects.filter(organization=organization)
        .annotate(current_revision_id=Subquery(latest_revision.values("id")[:1]))
        .annotate(
            has_activated_rules=Exists(
                RuleSet.objects.filter(
                    equipment=OuterRef("pk"),
                    equipment_revision_id=OuterRef("current_revision_id"),
                    activation__isnull=False,
                )
            )
        )
        .aggregate(
            total=Count("id"),
            draft=Count("id", filter=Q(status="draft")),
            active=Count("id", filter=Q(status="active")),
            archived=Count("id", filter=Q(status="archived")),
            active_with_activated_rules=Count(
                "id", filter=Q(status="active", has_activated_rules=True)
            ),
        )
    )
    assessment_query = Assessment.objects.filter(organization=organization)
    assessments = assessment_query.aggregate(
        total=Count("id"),
        compatible=Count("id", filter=Q(overall="compatible")),
        incompatible=Count("id", filter=Q(overall="incompatible")),
        indeterminate=Count("id", filter=Q(overall="indeterminate")),
    )
    assessments["recent"] = list(
        assessment_query.order_by("-created_at", "-id").values(
            "id", "product_id", "equipment_id", "overall", "summary", "created_at"
        )[:RECENT_LIMIT]
    )
    return {
        "generated_at": timezone.now(),
        "scope": "all_time",
        "organization": organization,
        "role": membership.role,
        "products": products,
        "imports": imports,
        "equipment": equipment,
        "assessments": assessments,
    }


class DashboardView(PrivateResponseView):
    @extend_schema(
        operation_id="organization_dashboard",
        responses=DashboardSerializer,
    )
    def get(self, request, organization_id):
        query = DashboardQuery(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        return Response(DashboardSerializer(overview(request.user, organization_id)).data)
