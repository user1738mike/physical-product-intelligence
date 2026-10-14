from rest_framework import serializers

from accounts.serializers import ProfileSerializer, StrictSerializer

from .models import Membership


class OrganizationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    slug = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class OrganizationCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=160)
    slug = serializers.RegexField(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)


class OrganizationUpdateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=160)


class OrganizationStateSerializer(StrictSerializer):
    is_active = serializers.BooleanField()


class MemberSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    user = ProfileSerializer(read_only=True)
    role = serializers.ChoiceField(choices=Membership.Role.choices, read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class MyMembershipSerializer(MemberSerializer):
    organization = OrganizationSerializer(read_only=True)


class AddMemberSerializer(StrictSerializer):
    username = serializers.CharField(max_length=150)
    role = serializers.ChoiceField(choices=["admin", "member"], default="member")


class RoleSerializer(StrictSerializer):
    role = serializers.ChoiceField(choices=["admin", "member"])


class TransferSerializer(StrictSerializer):
    membership_id = serializers.UUIDField()


class AuditSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    timestamp = serializers.DateTimeField(read_only=True)
    actor_id = serializers.IntegerField(read_only=True, allow_null=True)
    action = serializers.CharField(read_only=True)
    target_type = serializers.CharField(read_only=True)
    target_id = serializers.CharField(read_only=True)
    outcome = serializers.CharField(read_only=True)
    metadata = serializers.JSONField(read_only=True)


class PageSerializer(serializers.Serializer):
    count = serializers.IntegerField(read_only=True)
    next = serializers.URLField(read_only=True, allow_null=True)
    previous = serializers.URLField(read_only=True, allow_null=True)


class MembershipPageSerializer(PageSerializer):
    results = MyMembershipSerializer(many=True, read_only=True)


class MemberPageSerializer(PageSerializer):
    results = MemberSerializer(many=True, read_only=True)


class AuditPageSerializer(PageSerializer):
    results = AuditSerializer(many=True, read_only=True)
