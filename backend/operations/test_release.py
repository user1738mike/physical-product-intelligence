import io
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings

from ingestion import ai_provider


class ReleaseTests(TestCase):
    def test_csrf_denial_and_invalid_host_are_not_cacheable(self):
        from rest_framework.test import APIClient

        client = APIClient(enforce_csrf_checks=True)
        for response in (
            client.post("/api/v1/auth/login/", {}, format="json"),
            client.get("/api/v1/auth/me/", HTTP_HOST="evil.invalid"),
        ):
            self.assertIn("no-store", response["Cache-Control"])

    def test_migration_identity_mismatch_never_runs_migrations(self):
        with patch("operations.management.commands.release_migrate.call_command") as migrate:
            with self.assertRaises(CommandError):
                call_command("release_migrate", confirm_database="wrong")
        migrate.assert_not_called()

    def test_controlled_migration_lock_released_without_schema_mutation_in_test(self):
        with patch("operations.management.commands.release_migrate.call_command") as migrate:
            call_command(
                "release_migrate",
                confirm_database=connection.settings_dict["NAME"],
                stdout=io.StringIO(),
            )
        self.assertEqual(migrate.call_count, 2)

    @override_settings(
        READINESS_PRIVATE_STORAGE=True, INGESTION_SCANNER="ingestion.scanning.clamd_scan"
    )
    def test_unavailable_required_scanner_is_unready(self):
        with patch("operations.views.scanner_ready", return_value=False):
            self.assertEqual(self.client.get("/api/v1/health/ready/").status_code, 503)

    @override_settings(AI_EXTRACTION_ENABLED=True, AI_EXTRACTION_PROVIDER="recorded")
    def test_production_cannot_enable_recorded_provider_by_provider_name(self):
        self.assertEqual(ai_provider.availability(), (False, "unsupported_provider"))

    @override_settings(
        AI_EXTRACTION_ENABLED=True, AI_EXTRACTION_PROVIDER="recorded", ALLOW_REHEARSAL_PROVIDER=True
    )
    def test_explicit_recorded_provider_never_constructs_openai_adapter(self):
        with patch("ingestion.ai_provider.OpenAIProvider", side_effect=AssertionError("No live")):
            provider = ai_provider.configured_provider()
            response, usage = provider.extract([{"id": 1, "text": "Weight: 1200 g"}])
        self.assertIn('"value": "1200"', response)
        self.assertEqual(usage["total_tokens"], 0)

    @override_settings(
        AI_EXTRACTION_ENABLED=False,
        AI_EXTRACTION_PROVIDER="recorded",
        ALLOW_REHEARSAL_PROVIDER=True,
    )
    def test_disabled_fixture_stays_disabled(self):
        self.assertEqual(ai_provider.availability(), (False, "disabled"))
