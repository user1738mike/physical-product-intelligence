import io
import json
import os
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier, Event
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from integrations.models import Credential
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts import recovery
from accounts.models import RecoveryGrant
from audit.models import AuditEvent
from operations.models import RateBucket

OLD = "fixture-old!Password2026"
NEW = "fixture-new!Password2027"


class RecoveryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("recover-user", password=OLD)
        self.operator = get_user_model().objects.create_user("recover-operator", is_staff=True)
        self.token = recovery.issue(self.operator, self.user.username, "CASE-123")
        self.client = APIClient(enforce_csrf_checks=True)

    def post(self, token=None, password=NEW, csrf=True):
        headers = {}
        if csrf:
            headers["HTTP_X_CSRFTOKEN"] = self.client.get("/api/v1/auth/csrf/").json()["csrfToken"]
        return self.client.post(
            "/api/v1/auth/recover/",
            {"token": token or self.token, "new_password": password},
            format="json",
            **headers,
        )

    def test_csrf_password_policy_single_use_and_all_session_revocation(self):
        other = APIClient()
        other.force_login(self.user)
        self.assertEqual(self.post(csrf=False).status_code, 403)
        self.assertEqual(self.post(password="weak").status_code, 400)
        self.assertIsNone(RecoveryGrant.objects.get().consumed_at)
        response = self.post()
        self.assertEqual(response.status_code, 204)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(other.get("/api/v1/auth/me/").status_code, 403)
        self.assertEqual(self.post().status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
        self.assertFalse(self.user.is_staff)

    def test_wrong_expired_and_inactive_are_generic_and_no_user_creation(self):
        bad = self.token[:-1] + ("A" if self.token[-1] != "A" else "B")
        response = self.post(token=bad)
        expected = response.json()
        self.assertEqual(response.status_code, 400)
        # Expiration is immutable: advance the clock rather than editing history.
        with patch(
            "accounts.recovery.timezone.now", return_value=timezone.now() + timedelta(minutes=16)
        ):
            self.assertEqual(self.post().json(), expected)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.post().json(), expected)
        self.assertEqual(self.post(token="bad").json(), expected)
        self.assertEqual(get_user_model().objects.count(), 2)

    def test_new_issuance_revokes_old_and_database_contains_no_raw_secret(self):
        newer = recovery.issue(self.operator, self.user.username, "CASE-124")
        self.assertEqual(self.post().status_code, 400)
        self.assertEqual(self.post(token=newer).status_code, 204)
        stored = json.dumps(list(RecoveryGrant.objects.values()), default=str)
        for value in (self.token.split(".")[1], newer.split(".")[1], OLD, NEW):
            self.assertNotIn(value, stored)
        self.assertTrue(AuditEvent.objects.filter(action="account.recovered").exists())

    def test_password_change_reauthenticates_and_revokes_issued_credentials(self):
        credential = Credential.objects.create(
            organization=self.organization(),
            issuer=self.user,
            name="Fixture",
            verifier="a" * 64,
            scopes=["catalog:read"],
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(self.user)
        token = self.client.get("/api/v1/auth/csrf/").json()["csrfToken"]
        path = "/api/v1/auth/password/"
        values = {"current_password": "wrong", "new_password": NEW}
        self.assertEqual(
            self.client.post(path, values, format="json", HTTP_X_CSRFTOKEN=token).status_code, 400
        )
        values["current_password"] = OLD
        self.assertEqual(
            self.client.post(path, values, format="json", HTTP_X_CSRFTOKEN=token).status_code, 204
        )
        credential.refresh_from_db()
        self.assertIsNotNone(credential.revoked_at)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 403)
        self.assertEqual(self.post().status_code, 400)

    def organization(self):
        from organizations.services import create_organization

        return create_organization(self.user, name="Recovery fixture", slug="recovery-fixture")

    def test_grants_require_operator_and_privileged_targets_are_excluded(self):
        from rest_framework.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            recovery.issue(self.user, self.operator.username, "CASE-125")
        with self.assertRaises(get_user_model().DoesNotExist):
            recovery.issue(self.operator, self.operator.username, "CASE-125")

    def test_command_protects_link_and_never_prints_or_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "recovery-link"
            output = io.StringIO()
            call_command(
                "issue_recovery",
                actor=self.operator.username,
                user=self.user.username,
                case_reference="CASE-126",
                output=str(path),
                stdout=output,
            )
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            link = path.read_text()
            self.assertTrue(link.startswith("/account/recover#token="))
            self.assertNotIn(link.split("token=")[1].strip(), output.getvalue())
            with self.assertRaises(CommandError):
                call_command(
                    "issue_recovery",
                    actor=self.operator.username,
                    user=self.user.username,
                    case_reference="CASE-127",
                    output=str(path),
                    stdout=output,
                )
            self.assertEqual(path.read_text(), link)
            os.chmod(folder, 0o755)
            with self.assertRaises(CommandError):
                call_command(
                    "issue_recovery",
                    actor=self.operator.username,
                    user=self.user.username,
                    case_reference="CASE-128",
                    output=str(Path(folder) / "another"),
                    stdout=output,
                )

    def test_recovery_attempts_are_shared_limited(self):
        for _ in range(10):
            self.assertEqual(self.post(token="bad").status_code, 400)
        self.assertEqual(self.post(token="bad").status_code, 429)
        self.assertTrue(RateBucket.objects.exists())

    def test_runtime_cannot_issue_or_rewrite_but_can_redeem(self):
        role = connection.ops.quote_name("ppi_recovery_test_" + uuid.uuid4().hex[:12])
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {role} NOLOGIN NOINHERIT")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            cursor.execute(
                f"GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {role}"
            )
            cursor.execute(f"SET LOCAL ROLE {role}")
        try:
            for query in (
                "UPDATE accounts_recoverygrant SET verifier=repeat('b',64)",
                "DELETE FROM accounts_recoverygrant",
                "INSERT INTO accounts_recoverygrant SELECT gen_random_uuid(),created_at,"
                "expires_at,verifier,password_fingerprint,case_reference,consumed_at,revoked_at,"
                "issued_by_id,user_id FROM accounts_recoverygrant",
            ):
                with (
                    self.assertRaises(IntegrityError),
                    transaction.atomic(),
                    connection.cursor() as cursor,
                ):
                    cursor.execute(query)
            recovery.redeem(self.token, NEW)
            self.assertIsNotNone(RecoveryGrant.objects.get().consumed_at)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")


class RecoveryConcurrencyTests(TransactionTestCase):
    def test_password_lock_does_not_block_unrelated_tenant_audit_foreign_keys(self):
        from organizations.services import create_organization

        user = get_user_model().objects.create_user("recover-fk", password=OLD)
        operator = get_user_model().objects.create_user("recover-fk-operator", is_staff=True)
        token = recovery.issue(operator, user.username, "CASE-FK")
        held, written = Event(), Event()
        original = recovery.set_password

        def paused(*args):
            held.set()
            self.assertTrue(written.wait(timeout=10), "Password lock blocked unrelated FK writes")
            return original(*args)

        def reset():
            close_old_connections()
            try:
                recovery.redeem(token, NEW)
            finally:
                close_old_connections()

        def write():
            close_old_connections()
            try:
                self.assertTrue(held.wait(timeout=10))
                create_organization(user, name="Concurrent organization", slug="recovery-fk")
                written.set()
            finally:
                close_old_connections()

        with (
            patch("accounts.recovery.set_password", side_effect=paused),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            futures = [executor.submit(reset), executor.submit(write)]
            for future in futures:
                future.result(timeout=20)

    def test_two_redemptions_have_one_winner(self):
        user = get_user_model().objects.create_user("recover-race", password=OLD)
        operator = get_user_model().objects.create_user("recover-race-operator", is_staff=True)
        token = recovery.issue(operator, user.username, "CASE-RACE")
        barrier = Barrier(2)

        def work():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    recovery.redeem(token, NEW)
                    return "reset"
                except ValidationError:
                    return "denied"
            finally:
                close_old_connections()

        self.assertEqual(connection.vendor, "postgresql")
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sorted(executor.map(lambda _: work(), range(2))), ["denied", "reset"])
