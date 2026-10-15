import json
import os
from pathlib import Path

from django.conf import settings
from django.core.files.storage import storages
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Count, Min
from django.utils import timezone

from ingestion.ai_provider import availability
from ingestion.models import ImportJob
from operations.database import runtime_role_privileged


class Command(BaseCommand):
    help = (
        "Operator-only bounded status/metrics. Never calls a provider or prints environment values."
    )

    def handle(self, *args, **options):
        executor = MigrationExecutor(connection)
        root = Path(storages["ingestion"].location)
        configured, reason = availability()
        waiting = ImportJob.objects.filter(mode="ai", status__in=["uploaded", "processing"])
        oldest = waiting.aggregate(at=Min("created_at"))["at"]
        privileged = runtime_role_privileged()
        self.stdout.write(
            json.dumps(
                {
                    "migrations_current": not executor.migration_plan(
                        executor.loader.graph.leaf_nodes()
                    ),
                    "database_role_privileged": privileged,
                    "private_storage_writable": root.is_dir()
                    and os.access(root, os.R_OK | os.W_OK),
                    "scanner_configured": bool(settings.INGESTION_SCANNER),
                    "ai_configured": configured,
                    "ai_configuration_status": reason,
                    "provider_reachability": "not_checked",
                    "jobs_by_state": list(
                        ImportJob.objects.values("mode", "status")
                        .annotate(count=Count("id"))
                        .order_by("mode", "status")
                    ),
                    "waiting_extractions": waiting.count(),
                    "oldest_waiting_seconds": max(0, int((timezone.now() - oldest).total_seconds()))
                    if oldest
                    else 0,
                    "limiter": "shared_database_fixed_window",
                }
            )
        )
