"""Only new synthetic fixtures in the explicitly isolated local rehearsal."""

import re
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.db import connection, transaction

from commercial import services
from commercial.models import FEATURES, METERS

from .models import PlanPolicy


def require():
    if (
        not getattr(settings, "INTEGRATION_TEST_TRANSPORT", False)
        or not getattr(settings, "ALLOW_REHEARSAL_PROVIDER", False)
        or not re.fullmatch(r"ppi_rehearsal_[a-f0-9]{10}", connection.settings_dict["NAME"])
    ):
        raise CommandError("Only an isolated synthetic integration rehearsal is permitted.")


@transaction.atomic
def enable_plan(org):
    require()
    actor = get_user_model().objects.create_user(
        "integration-operator-" + uuid.uuid4().hex[:12], is_staff=True
    )
    actor.set_unusable_password()
    actor.save()
    plan = services.publish(
        actor,
        code="integration-" + uuid.uuid4().hex[:12],
        version=2,
        name="Synthetic integration allowance",
        policy={**{key: True for key in FEATURES}, **{key + "_limit": None for key in METERS}},
        reason="New synthetic integration verification",
    )
    PlanPolicy.objects.create(
        plan=plan,
        credentials_limit=3,
        destinations_limit=2,
        api_enabled=True,
        webhooks_enabled=True,
    )
    services.assign(actor, org, plan, reason="New synthetic integration allowance")
    return actor
