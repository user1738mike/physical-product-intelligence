import logging

from django.db import DatabaseError, connection
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

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
        except DatabaseError:
            logger.warning("database_unavailable")
            return Response({"status": "unavailable", "service": "backend"}, status=503)
        return Response({"status": "ok", "service": "backend"})
