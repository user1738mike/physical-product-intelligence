import json
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from integrations.rehearsal import require

from ingestion import services
from ingestion.models import ImportJob
from organizations.services import create_organization


class Command(BaseCommand):
    help = "Create a new synthetic old unused file in the guarded local rehearsal only."

    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        require()
        owner = get_user_model().objects.get(username=options["owner"], is_active=True)
        org = create_organization(
            owner, name="Synthetic source retention", slug="retention-" + uuid.uuid4().hex[:12]
        )
        source = services.upload(
            owner,
            org.pk,
            SimpleUploadedFile(
                "unused-source.csv",
                b"sku,name\nUNUSED,Synthetic unused source\n",
                content_type="text/csv",
            ),
        )
        source = services.cancel(owner, org.pk, source.pk, {"expected_version": source.version})
        ImportJob.objects.filter(pk=source.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        self.stdout.write(json.dumps({"organization_id": str(org.pk), "source_id": str(source.pk)}))
