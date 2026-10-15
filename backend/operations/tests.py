import importlib
import io
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError
from django.test import SimpleTestCase, TestCase

from operations.logging import JsonFormatter


class HealthTests(TestCase):
    def test_live_is_independent_of_database(self):
        with patch("operations.views.connection.cursor", side_effect=AssertionError("No DB")):
            response = self.client.get("/api/v1/health/live/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "backend"})
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_ready_uses_real_database(self):
        response = self.client.get("/api/v1/health/ready/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_database_failure_does_not_leak_details(self):
        with patch("operations.views.connection.cursor", side_effect=DatabaseError("secret-host")):
            response = self.client.get("/api/v1/health/ready/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable", "service": "backend"})
        self.assertNotIn(b"secret-host", response.content)

    def test_unexpected_database_result_is_not_ready(self):
        with patch("operations.views.connection.cursor") as cursor:
            cursor.return_value.__enter__.return_value.fetchone.return_value = (0,)
            response = self.client.get("/api/v1/health/ready/")
        self.assertEqual(response.status_code, 503)

    def test_request_id_is_bounded_and_query_is_not_logged(self):
        with self.assertLogs("operations.requests", level="INFO") as logs:
            response = self.client.get(
                "/api/v1/health/live/?token=private", HTTP_X_REQUEST_ID="x" * 65
            )
        self.assertEqual(len(response["X-Request-ID"]), 32)
        self.assertNotIn("private", str(logs.records[0].__dict__))
        valid = self.client.get("/api/v1/health/live/", HTTP_X_REQUEST_ID="trace_123")
        self.assertEqual(valid["X-Request-ID"], "trace_123")


class ProductionSettingsTests(SimpleTestCase):
    config = {
        "DJANGO_SECRET_KEY": "a9$Z7!" * 10,
        "DJANGO_ALLOWED_HOSTS": "api.example.com",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://app.example.com",
        "POSTGRES_DB": "ppi",
        "POSTGRES_USER": "ppi",
        "POSTGRES_PASSWORD": "8wX2!nmQ7#tL4@zV9$rH6&dK",
        "INGESTION_STORAGE_ROOT": str(Path(tempfile.gettempdir()) / "ppi-private-fixture"),
        "POSTGRES_HOST": "db",
        "POSTGRES_PORT": "5432",
    }

    def load_settings(self, values):
        name = "config.settings.production"
        sys.modules.pop(name, None)
        with patch.dict(os.environ, values, clear=True):
            try:
                return importlib.import_module(name)
            finally:
                sys.modules.pop(name, None)

    def test_required_environment_variables_fail_closed(self):
        for key in self.config:
            with self.subTest(key=key):
                values = self.config.copy()
                del values[key]
                with self.assertRaises(ImproperlyConfigured):
                    self.load_settings(values)

    def test_unsafe_values_are_rejected(self):
        for key, value in [
            ("DJANGO_SECRET_KEY", "replace-with-a-secret"),
            ("DJANGO_ALLOWED_HOSTS", "*"),
            ("DJANGO_CSRF_TRUSTED_ORIGINS", "http://app.example.com"),
            ("DJANGO_CSRF_TRUSTED_ORIGINS", "https://*.example.com"),
            ("POSTGRES_PASSWORD", "password"),
            ("DJANGO_ALLOWED_HOSTS", ".example.com"),
            ("INGESTION_STORAGE_ROOT", "relative/public"),
            ("TRUSTED_PROXY_CIDRS", "0.0.0.0/0"),
            ("TRUSTED_PROXY_CIDRS", "not-a-network"),
            ("DJANGO_TRUST_PROXY", "true"),
        ]:
            with self.subTest(key=key, value=value):
                with self.assertRaises(ImproperlyConfigured):
                    self.load_settings({**self.config, key: value})

    def test_secure_defaults_and_proxy_trust(self):
        settings = self.load_settings(self.config)
        self.assertFalse(settings.DEBUG)
        self.assertTrue(settings.SECURE_SSL_REDIRECT)
        self.assertTrue(settings.SESSION_COOKIE_SECURE)
        self.assertTrue(settings.CSRF_COOKIE_SECURE)
        self.assertFalse(hasattr(settings, "SECURE_PROXY_SSL_HEADER"))
        trusted = self.load_settings(
            {**self.config, "DJANGO_TRUST_PROXY": "true", "TRUSTED_PROXY_CIDRS": "127.0.0.1/32"}
        )
        self.assertEqual(trusted.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))


class LoggingTests(SimpleTestCase):
    def test_configured_server_handler_does_not_leak_query_values(self):
        logger = logging.getLogger("django.server")
        output = io.StringIO()
        self.assertTrue(logger.handlers)
        with patch.object(logger.handlers[0], "stream", output):
            logger.warning("GET /?token=private-fixture")
        self.assertNotIn("private-fixture", output.getvalue())
        self.assertIn("framework_http", output.getvalue())

    def test_framework_request_messages_cannot_leak_query_values(self):
        record = logging.LogRecord(
            "django.server", logging.INFO, "", 0, "GET /?token=private", (), None
        )
        formatted = JsonFormatter().format(record)
        self.assertNotIn("private", formatted)
        self.assertEqual(json.loads(formatted)["event"], "framework_http")
