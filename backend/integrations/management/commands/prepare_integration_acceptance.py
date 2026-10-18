import json
import uuid

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from integrations.rehearsal import enable_plan, require
from organizations.models import Membership
from organizations.services import create_organization


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True)
        parser.add_argument("--member", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        require()
        owner = get_user_model().objects.get(username=options["owner"])
        member = get_user_model().objects.get(username=options["member"])
        org = create_organization(
            owner,
            name="Synthetic warehouse integrations",
            slug="integration-browser-" + uuid.uuid4().hex[:12],
        )
        Membership.objects.create(organization=org, user=member, role="admin")
        enable_plan(org)
        self.stdout.write(json.dumps({"organization_id": str(org.pk)}))
