from django.db import IntegrityError
from drf_spectacular.utils import extend_schema
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from accounts.views import PrivateResponseView
from audit.models import AuditEvent

from . import services
from .models import Membership
from .serializers import (
    AddMemberSerializer,
    AuditPageSerializer,
    AuditSerializer,
    MemberPageSerializer,
    MemberSerializer,
    MembershipPageSerializer,
    MyMembershipSerializer,
    OrganizationCreateSerializer,
    OrganizationSerializer,
    OrganizationStateSerializer,
    OrganizationUpdateSerializer,
    RoleSerializer,
    TransferSerializer,
)


class TenantPagination(PageNumberPagination):
    page_size = 25


def page(request, query, serializer):
    paginator = TenantPagination()
    records = paginator.paginate_queryset(query, request)
    return paginator.get_paginated_response(serializer(records, many=True).data)


class MyMembershipsView(PrivateResponseView):
    @extend_schema(responses=MembershipPageSerializer)
    def get(self, request):
        return page(
            request,
            Membership.objects.filter(user=request.user).select_related("organization", "user"),
            MyMembershipSerializer,
        )


class OrganizationsView(PrivateResponseView):
    @extend_schema(request=OrganizationCreateSerializer, responses={201: OrganizationSerializer})
    def post(self, request):
        serializer = OrganizationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            organization = services.create_organization(request.user, **serializer.validated_data)
        except IntegrityError:
            return Response(
                {"detail": "Organization could not be created; choose a different slug."},
                status=409,
            )
        return Response(OrganizationSerializer(organization).data, status=201)


class OrganizationDetailView(PrivateResponseView):
    @extend_schema(responses=OrganizationSerializer)
    def get(self, request, organization_id):
        organization, _ = services.authorize(request.user, organization_id)
        return Response(OrganizationSerializer(organization).data)

    @extend_schema(request=OrganizationUpdateSerializer, responses=OrganizationSerializer)
    def patch(self, request, organization_id):
        serializer = OrganizationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = services.rename_organization(
            request.user, organization_id, **serializer.validated_data
        )
        return Response(OrganizationSerializer(organization).data)


class OrganizationStateView(PrivateResponseView):
    @extend_schema(request=OrganizationStateSerializer, responses=OrganizationSerializer)
    def post(self, request, organization_id):
        serializer = OrganizationStateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = services.set_active(
            request.user, organization_id, **serializer.validated_data
        )
        return Response(OrganizationSerializer(organization).data)


class MembersView(PrivateResponseView):
    @extend_schema(operation_id="organization_members_list", responses=MemberPageSerializer)
    def get(self, request, organization_id):
        organization, _ = services.authorize(request.user, organization_id)
        return page(
            request,
            Membership.objects.filter(organization=organization).select_related("user"),
            MemberSerializer,
        )

    @extend_schema(request=AddMemberSerializer, responses={201: MemberSerializer})
    def post(self, request, organization_id):
        serializer = AddMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = services.add_member(request.user, organization_id, **serializer.validated_data)
        return Response(MemberSerializer(member).data, status=201)


class MemberDetailView(PrivateResponseView):
    @extend_schema(responses=MemberSerializer)
    def get(self, request, organization_id, membership_id):
        organization, _ = services.authorize(request.user, organization_id)
        return Response(MemberSerializer(services.member_in(organization, membership_id)).data)

    @extend_schema(request=RoleSerializer, responses=MemberSerializer)
    def patch(self, request, organization_id, membership_id):
        serializer = RoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = services.change_role(
            request.user, organization_id, membership_id, **serializer.validated_data
        )
        return Response(MemberSerializer(member).data)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, organization_id, membership_id):
        services.remove_member(request.user, organization_id, membership_id)
        return Response(status=204)


class TransferView(PrivateResponseView):
    @extend_schema(request=TransferSerializer, responses=OrganizationSerializer)
    def post(self, request, organization_id):
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = services.transfer_ownership(
            request.user, organization_id, **serializer.validated_data
        )
        return Response(OrganizationSerializer(organization).data)


class AuditView(PrivateResponseView):
    @extend_schema(responses=AuditPageSerializer)
    def get(self, request, organization_id):
        organization, _ = services.authorize(
            request.user, organization_id, roles={services.OWNER, services.ADMIN}
        )
        return page(request, AuditEvent.objects.filter(organization=organization), AuditSerializer)
