import json
import secrets
import uuid

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from integrations.rehearsal import require

from accounts.recovery import issue
from organizations.services import create_organization


class Command(BaseCommand):
    @transaction.atomic
    def handle(self, *args, **options):
        require()
        operator = get_user_model().objects.create_user(
            "recovery-operator-" + uuid.uuid4().hex[:12],
            is_staff=True,
        )
        operator.set_unusable_password()
        operator.save(update_fields=["password"])
        passwords = [secrets.token_urlsafe(24) for _ in range(3)]
        user = get_user_model().objects.create_user(
            "recovery-browser-" + uuid.uuid4().hex[:12],
            password=passwords[0],
        )
        organization = create_organization(
            user, name="Synthetic recovery", slug="recovery-" + uuid.uuid4().hex[:12]
        )
        token = issue(operator, user.username, "SYNTHETIC-BROWSER")
        # Driver sends this directly on stdin to the isolated browser's tmpfs.
        self.stdout.write(
            json.dumps(
                {
                    "username": user.username,
                    "password": passwords[0],
                    "new_password": passwords[1],
                    "changed_password": passwords[2],
                    "token": token,
                    "organization_id": str(organization.pk),
                    "organization_slug": organization.slug,
                }
            )
        )
