import io
import json
import logging
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient, APIRequestFactory

from operations import recovery
from operations.database import runtime_role_privileged
from operations.logging import JsonFormatter
from operations.models import RateBucket
from operations.throttling import Limited, SharedRateThrottle, consume, peer_identity


class ReadinessAndLogTests(TestCase):
    def test_postgres_runtime_role_can_use_dml_but_cannot_disable_guards(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL role contracts")
        from django.contrib.auth import get_user_model

        from organizations.services import create_organization
        from products.services import create_product

        with connection.cursor() as cursor:
            cursor.execute("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")
            if not cursor.fetchone()[0]:
                self.skipTest("Isolated role fixture requires test-server administrative privilege")
            self.assertTrue(runtime_role_privileged())
            role = connection.ops.quote_name("ppi_phase7_test_" + uuid.uuid4().hex[:12])
            # All role/grant creation is rolled back with this isolated TestCase transaction.
            cursor.execute(f"CREATE ROLE {role} NOLOGIN NOINHERIT")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            cursor.execute(
                f"GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {role}"
            )
            cursor.execute(f"GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
        actor = get_user_model().objects.create_user("runtime-role-fixture")
        org = create_organization(actor, name="Runtime fixture", slug="runtime-role-fixture")
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL ROLE {role}")
        try:
            self.assertFalse(runtime_role_privileged())
            product = create_product(
                actor,
                org.pk,
                {"sku": "RUNTIME", "revision": {"name": "Fixture", "change_reason": "Role test"}},
            )
            client = APIClient()
            client.force_authenticate(actor)
            self.assertEqual(
                client.get(f"/api/v1/organizations/{org.pk}/products/{product.pk}/").status_code,
                200,
            )
            with (
                self.assertRaises(DatabaseError),
                transaction.atomic(),
                connection.cursor() as cursor,
            ):
                cursor.execute("ALTER TABLE products_productrevision DISABLE TRIGGER ALL")
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    @override_settings(READINESS_DATABASE_ROLE=True)
    def test_elevated_runtime_role_is_not_production_ready(self):
        with patch("operations.views.runtime_role_privileged", return_value=True):
            self.assertEqual(self.client.get("/api/v1/health/ready/").status_code, 503)

    def test_pending_migration_is_unready_without_details(self):
        with patch("operations.views.MigrationExecutor") as executor:
            executor.return_value.migration_plan.return_value = ["pending-secret-table"]
            response = self.client.get("/api/v1/health/ready/")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"pending-secret", response.content)

    @override_settings(READINESS_PRIVATE_STORAGE=True, INGESTION_SCANNER="")
    def test_required_scanner_storage_policy_blocks_readiness(self):
        self.assertEqual(self.client.get("/api/v1/health/ready/").status_code, 503)

    def test_host_validation_applies_even_to_liveness(self):
        self.assertEqual(
            self.client.get("/api/v1/health/live/", HTTP_HOST="evil.invalid").status_code, 400
        )

    def test_secret_like_unknown_paths_are_not_logged(self):
        with self.assertLogs("operations.requests", level="INFO") as logs:
            self.client.get("/api/v1/private-secret-token/")
        self.assertEqual(logs.records[0].path, "unmatched")
        self.assertNotIn("private-secret-token", str(logs.records[0].__dict__))

    def test_formatter_suppresses_unknown_messages_and_control_values(self):
        record = logging.LogRecord(
            "operations.any", logging.INFO, "", 0, "secret-key-value", (), None
        )
        record.request_id = "bad\nsecret"
        record.duration_ms = float("nan")
        formatted = JsonFormatter().format(record)
        self.assertNotIn("secret", formatted)
        self.assertNotIn("NaN", formatted)


class SharedLimiterTests(TestCase):
    def test_limit_is_shared_and_resets_at_window_boundary(self):
        consume(["opaque"], 2, 60, 100)
        consume(["opaque"], 2, 60, 100)
        with self.assertRaises(Limited):
            consume(["opaque"], 2, 60, 101)
        self.assertEqual(RateBucket.objects.get().count, 2)
        consume(["opaque"], 2, 60, 120)
        self.assertEqual(RateBucket.objects.get().count, 1)

    def test_multi_subject_denial_rolls_back_other_counter(self):
        consume(["b"], 1, 60, 100)
        with self.assertRaises(Limited):
            consume(["a", "b"], 1, 60, 100)
        self.assertFalse(RateBucket.objects.filter(key="a").exists())

    def test_forwarded_variations_do_not_bypass_peer_identity(self):
        request = APIRequestFactory().post(
            "/", HTTP_X_FORWARDED_FOR="8.8.8.8", HTTP_X_REAL_IP="9.9.9.9"
        )
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        self.assertEqual(peer_identity(request), "127.0.0.1")
        with override_settings(TRUSTED_PROXY_CIDRS=["127.0.0.1/32"]):
            self.assertEqual(peer_identity(request), "9.9.9.9")

    def test_429_wait_and_fixed_window_do_not_store_raw_addresses(self):
        request = APIRequestFactory().post("/api/v1/auth/login/")
        request.user = AnonymousUser()
        view = SimpleNamespace(throttle_scope="login", kwargs={})
        limiter = SharedRateThrottle()
        with (
            patch("operations.throttling.api_settings.DEFAULT_THROTTLE_RATES", {"login": "1/min"}),
            patch("operations.throttling.time.time", return_value=100),
        ):
            self.assertTrue(limiter.allow_request(request, view))
            self.assertFalse(SharedRateThrottle().allow_request(request, view))
        self.assertEqual(limiter.wait(), 20)
        self.assertNotIn("127.0.0.1", RateBucket.objects.get().key)

    def test_database_failure_fails_closed_with_sanitized_503(self):
        with patch("operations.throttling.consume", side_effect=DatabaseError("secret connection")):
            response = APIClient().post(
                "/api/v1/auth/login/", {"username": "someone", "password": "private"}, format="json"
            )
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"secret", response.content)

    def test_pruning_is_dry_run_by_default(self):
        consume(["expired"], 1, 60, 1)
        output = io.StringIO()
        call_command("prune_rate_buckets", stdout=output)
        self.assertFalse(json.loads(output.getvalue())["applied"])
        self.assertTrue(RateBucket.objects.exists())


class ConcurrentLimiterTests(TransactionTestCase):
    def test_concurrent_process_admission_never_exceeds_shared_limit(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL concurrency")
        barrier = Barrier(8)

        def run(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                consume(["concurrent"], 3, 60, 100)
                return True
            except Limited:
                return False
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(run, range(8)))
        self.assertEqual(sum(results), 3)
        self.assertEqual(RateBucket.objects.get().count, 3)


class RecoveryGuardTests(TestCase):
    def test_backup_requires_exact_database_and_new_directory(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                recovery.backup(Path(root) / "new", "wrong-target", "not-called")
            with self.assertRaises(FileExistsError):
                recovery.backup(root, connection.settings_dict["NAME"], "not-called")

    def test_private_key_paths_reject_traversal_and_public_paths(self):
        root = Path(tempfile.gettempdir()) / "root"
        for key in ["../secret.txt", "/secret.txt", "x/../../a.csv", "https://evil.invalid/a.pdf"]:
            with self.assertRaises(ValueError):
                recovery.safe_path(root, key)
        self.assertTrue(
            recovery.safe_path(root, f"{uuid.uuid4()}/{uuid.uuid4().hex}.pdf").is_relative_to(root)
        )

    def test_restore_refuses_working_or_nonempty_database_before_external_tool(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "manifest.json").write_text(
                json.dumps({"format": "ppi-backup-v1", "source_database": "source"})
            )
            with patch("operations.recovery.pg_tool") as external:
                with self.assertRaises(ValueError):
                    recovery.restore(
                        root, connection.settings_dict["NAME"], root / "media", "not-called"
                    )
                with patch.dict(connection.settings_dict, {"NAME": "ppi_restore_fixture"}):
                    with self.assertRaises(ValueError):
                        recovery.restore(root, "ppi_restore_fixture", root / "media", "not-called")
            external.assert_not_called()

    def test_backup_subprocess_credentials_are_never_command_arguments(self):
        with patch("operations.recovery.subprocess.run") as run:
            recovery.pg_tool("pg_dump", ["--format=custom"])
        kwargs = run.call_args.kwargs
        self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
        self.assertIn("PGPASSWORD", kwargs["env"])
        self.assertNotIn("PGPASSWORD", " ".join(run.call_args.args[0]))


class ProxyTests(SimpleTestCase):
    def test_untrusted_forwarded_https_cannot_change_scheme(self):
        from operations.middleware import TrustedProxyMiddleware

        request = APIRequestFactory().get(
            "/", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
        )
        middleware = TrustedProxyMiddleware(lambda r: r.is_secure())
        with override_settings(
            SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"), TRUSTED_PROXY_CIDRS=[]
        ):
            self.assertFalse(middleware(request))

    def test_trusted_peer_can_supply_canonical_https(self):
        from operations.middleware import TrustedProxyMiddleware

        request = APIRequestFactory().get(
            "/", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
        )
        with override_settings(
            SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
            TRUSTED_PROXY_CIDRS=["127.0.0.1/32"],
        ):
            self.assertTrue(TrustedProxyMiddleware(lambda r: r.is_secure())(request))
