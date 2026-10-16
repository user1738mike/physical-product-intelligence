import logging
import os
from pathlib import Path

from django.conf import settings
from django.core.files.storage import storages
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.scanning import scanner_ready

from .database import runtime_role_privileged

logger = logging.getLogger("operations.health")


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "unavailable"])
    service = serializers.CharField()


class LiveView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses={200: HealthSerializer}, auth=[], summary="Process liveness")
    def get(self, request):
        return Response({"status": "ok", "service": "backend"})


class ReadyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        responses={200: HealthSerializer, 503: HealthSerializer},
        auth=[],
        summary="Database readiness",
    )
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    raise DatabaseError("Unexpected database response")
            executor = MigrationExecutor(connection)
            if executor.migration_plan(executor.loader.graph.leaf_nodes()):
                raise DatabaseError("Migrations pending")
            if settings.READINESS_DATABASE_ROLE and runtime_role_privileged():
                raise DatabaseError("Runtime database role policy unavailable")
            if settings.READINESS_PRIVATE_STORAGE:
                root = Path(storages["ingestion"].location)
                if (
                    not root.is_dir()
                    or not os.access(root, os.R_OK | os.W_OK)
                    or not settings.INGESTION_SCANNER
                ):
                    raise DatabaseError("Private storage/scanner configuration unavailable")
                if (
                    settings.INGESTION_SCANNER == "ingestion.scanning.clamd_scan"
                    and not scanner_ready()
                ):
                    raise DatabaseError("Required scanner unavailable")
        except (DatabaseError, OSError, ValueError):
            logger.warning("readiness_unavailable")
            return Response({"status": "unavailable", "service": "backend"}, status=503)
        return Response({"status": "ok", "service": "backend"})
