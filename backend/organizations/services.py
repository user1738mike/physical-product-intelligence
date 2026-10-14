from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from audit.services import record

from .models import Membership, Organization

OWNER = Membership.Role.OWNER
ADMIN = Membership.Role.ADMIN
MEMBER = Membership.Role.MEMBER


def authorize(actor, organization_id, *, roles=None, allow_suspended=False, lock=False):
    if not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied("Authentication required.")
    query = Organization.objects.filter(memberships__user=actor)
    if not allow_suspended:
        query = query.filter(is_active=True)
    if lock:
        query = query.select_for_update(of=("self",))
    try:
        organization = query.get(pk=organization_id)
        membership = Membership.objects.get(organization=organization, user=actor)
    except (Organization.DoesNotExist, Membership.DoesNotExist) as error:
        raise NotFound("Organization not found.") from error
    if roles is not None and membership.role not in roles:
        raise PermissionDenied("Your role does not permit this action.")
    return organization, membership


def member_in(organization, membership_id):
    try:
        return Membership.objects.select_related("user").get(
            organization=organization, pk=membership_id
        )
    except Membership.DoesNotExist as error:
        raise NotFound("Membership not found.") from error


@transaction.atomic
def create_organization(actor, *, name, slug):
    if not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied("Authentication required.")
    organization = Organization.objects.create(name=name, slug=slug)
    member = Membership.objects.create(organization=organization, user=actor, role=OWNER)
    record(
        "organization.created",
        actor=actor,
        organization=organization,
        target_type="organization",
        target_id=organization.pk,
    )
    record(
        "membership.created",
        actor=actor,
        organization=organization,
        target_type="membership",
        target_id=member.pk,
        metadata={"role": OWNER},
    )
    return organization


@transaction.atomic
def rename_organization(actor, organization_id, *, name):
    organization, _ = authorize(actor, organization_id, roles={OWNER, ADMIN}, lock=True)
    organization.name = name
    organization.save(update_fields=["name", "updated_at"])
    record(
        "organization.updated",
        actor=actor,
        organization=organization,
        target_type="organization",
        target_id=organization.pk,
    )
    return organization


@transaction.atomic
def set_active(actor, organization_id, *, is_active):
    organization, _ = authorize(
        actor, organization_id, roles={OWNER}, allow_suspended=True, lock=True
    )
    if organization.is_active != is_active:
        organization.is_active = is_active
        organization.save(update_fields=["is_active", "updated_at"])
        record(
            "organization.reactivated" if is_active else "organization.suspended",
            actor=actor,
            organization=organization,
            target_type="organization",
            target_id=organization.pk,
        )
    return organization


@transaction.atomic
def add_member(actor, organization_id, *, username, role=MEMBER):
    organization, caller = authorize(actor, organization_id, roles={OWNER, ADMIN}, lock=True)
    if role not in {ADMIN, MEMBER} or (caller.role != OWNER and role != MEMBER):
        raise PermissionDenied("Only owners can grant administrative privileges.")
    try:
        user = get_user_model().objects.get(username=username, is_active=True)
    except get_user_model().DoesNotExist as error:
        raise NotFound("Account not found.") from error
    try:
        with transaction.atomic():
            member = Membership.objects.create(organization=organization, user=user, role=role)
    except IntegrityError as error:
        raise ValidationError("Membership already exists.") from error
    record(
        "membership.created",
        actor=actor,
        organization=organization,
        target_type="membership",
        target_id=member.pk,
        metadata={"role": role},
    )
    return member


@transaction.atomic
def change_role(actor, organization_id, membership_id, *, role):
    organization, _ = authorize(actor, organization_id, roles={OWNER}, lock=True)
    member = member_in(organization, membership_id)
    if member.role == OWNER or role not in {ADMIN, MEMBER}:
        raise ValidationError("Use ownership transfer; the owner cannot be demoted.")
    previous = member.role
    member.role = role
    member.save(update_fields=["role"])
    record(
        "membership.role_changed",
        actor=actor,
        organization=organization,
        target_type="membership",
        target_id=member.pk,
        metadata={"previous_role": previous, "role": role},
    )
    return member


@transaction.atomic
def remove_member(actor, organization_id, membership_id):
    organization, caller = authorize(actor, organization_id, roles={OWNER, ADMIN}, lock=True)
    member = member_in(organization, membership_id)
    if member.role == OWNER:
        raise ValidationError("The owner cannot be removed; transfer ownership first.")
    if caller.role == ADMIN and member.role != MEMBER:
        raise PermissionDenied("Administrators can remove only ordinary members.")
    record(
        "membership.removed",
        actor=actor,
        organization=organization,
        target_type="membership",
        target_id=member.pk,
        metadata={"role": member.role},
    )
    member.delete()


@transaction.atomic
def transfer_ownership(actor, organization_id, *, membership_id):
    organization, caller = authorize(actor, organization_id, roles={OWNER}, lock=True)
    target = member_in(organization, membership_id)
    if not target.user.is_active or target.pk == caller.pk:
        raise ValidationError("Choose another active member.")
    previous = target.role
    # Demote first to respect the database's single-owner partial unique constraint.
    caller.role = ADMIN
    caller.save(update_fields=["role"])
    target.role = OWNER
    target.save(update_fields=["role"])
    record(
        "ownership.transferred",
        actor=actor,
        organization=organization,
        target_type="membership",
        target_id=target.pk,
        metadata={"previous_role": previous, "role": OWNER},
    )
    record(
        "membership.role_changed",
        actor=actor,
        organization=organization,
        target_type="membership",
        target_id=caller.pk,
        metadata={"previous_role": OWNER, "role": ADMIN},
    )
    return organization
