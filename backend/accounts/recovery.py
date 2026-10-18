import hashlib
import re
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from audit.services import record
from commercial.services import operator
from integrations.models import Credential

from .models import RecoveryGrant


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


@transaction.atomic
def issue(actor, username, case_reference):
    operator(actor)
    if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,120}", case_reference):
        raise ValidationError("A non-personal support case reference is required.")
    user = (
        get_user_model()
        .objects.select_for_update(no_key=True)
        .get(username=username, is_active=True, is_staff=False, is_superuser=False)
    )
    RecoveryGrant.objects.filter(user=user, consumed_at=None, revoked_at=None).update(
        revoked_at=timezone.now()
    )
    secret = secrets.token_urlsafe(32)
    item = RecoveryGrant.objects.create(
        user=user,
        issued_by=actor,
        expires_at=timezone.now() + timedelta(minutes=15),
        verifier=fingerprint(secret),
        password_fingerprint=fingerprint(user.password),
        case_reference=case_reference,
    )
    record("account.recovery_issued", actor=actor, target_type="user", target_id=user.pk)
    return f"{item.pk.hex}.{secret}"


def set_password(user, password):
    try:
        validate_password(password, user)
    except DjangoValidationError as error:
        raise ValidationError({"new_password": error.messages}) from None
    if user.check_password(password):
        raise ValidationError({"new_password": ["Choose a different password."]})
    user.set_password(password)
    user.save(update_fields=["password"])
    now = timezone.now()
    RecoveryGrant.objects.filter(user=user, consumed_at=None, revoked_at=None).update(
        revoked_at=now
    )
    Credential.objects.filter(issuer=user, revoked_at=None).update(revoked_at=now)


@transaction.atomic
def redeem(token, password):
    invalid = ValidationError("Recovery link is invalid or expired.")
    if not re.fullmatch(r"[a-f0-9]{32}\.[A-Za-z0-9_-]{43}", token):
        raise invalid
    identifier, secret = token.split(".")
    grant = RecoveryGrant.objects.filter(pk=identifier).first()
    if grant is None:
        raise invalid
    # Global identity lock serializes redemption, password change and new issuance.
    user = get_user_model().objects.select_for_update(no_key=True).get(pk=grant.user_id)
    grant.refresh_from_db()
    if (
        not user.is_active
        or user.is_staff
        or user.is_superuser
        or grant.consumed_at
        or grant.revoked_at
        or grant.expires_at <= timezone.now()
        or not secrets.compare_digest(grant.verifier, fingerprint(secret))
        or not secrets.compare_digest(grant.password_fingerprint, fingerprint(user.password))
    ):
        raise invalid
    # Consume first in the same transaction; invalid password rolls this back.
    grant.consumed_at = timezone.now()
    grant.save(update_fields=["consumed_at"])
    set_password(user, password)
    record("account.recovered", actor=user)


@transaction.atomic
def change(user_id, old_password, new_password):
    user = get_user_model().objects.select_for_update(no_key=True).get(pk=user_id)
    if not user.is_active or not user.check_password(old_password):
        raise ValidationError("Current password is incorrect.")
    set_password(user, new_password)
    record("account.password_changed", actor=user)
