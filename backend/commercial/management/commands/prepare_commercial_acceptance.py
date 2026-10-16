"""Synthetic-only browser fixtures, inaccessible to deployed production settings."""

import json
import re
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from commercial import services
from organizations.services import add_member, create_organization


class Command(BaseCommand):
    help = "Create new synthetic commercial browser fixtures only in isolated rehearsal databases."

    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True)
        parser.add_argument("--member", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        if not getattr(settings, "ALLOW_REHEARSAL_PROVIDER", False) or not re.fullmatch(
            r"ppi_rehearsal_[a-f0-9]{10}", connection.settings_dict["NAME"]
        ):
            raise CommandError("Isolated synthetic rehearsal required")
        users = get_user_model()
        owner = users.objects.get(username=options["owner"])
        member = users.objects.get(username=options["member"])
        suffix = uuid.uuid4().hex[:12]
        operator = users.objects.create_user("commercial-acceptance-" + suffix, is_staff=True)
        policy = {key: value for key, value in services.PILOT.items() if key != "name"}
        plan = services.publish(
            operator,
            code="acceptance-" + suffix,
            version=1,
            name="Synthetic finite acceptance",
            policy={
                **policy,
                "active_products_limit": 0,
                "assessments_limit": 0,
                "extractions_limit": 0,
            },
            reason="Synthetic acceptance setup",
        )
        result = {}
        for state in ("exhausted", "suspended", "expired", "admin"):
            org = create_organization(
                owner, name="Synthetic " + state, slug="commercial-" + state + "-" + suffix
            )
            assignment = services.assign(operator, org, plan, reason="Synthetic acceptance setup")
            if state == "suspended":
                services.transition(
                    operator, org, assignment.pk, action="suspend", reason="Synthetic acceptance"
                )
            elif state == "expired":
                # Normal scheduled expiry, elapsed by the later commercial browser checks.
                services.transition(
                    operator,
                    org,
                    assignment.pk,
                    action="expire",
                    reason="Synthetic acceptance",
                    ends_at=timezone.now() + timedelta(seconds=2),
                )
            elif state == "admin":
                add_member(owner, org.pk, username=member.username, role="admin")
            result[state] = str(org.pk)
        self.stdout.write(json.dumps(result))
