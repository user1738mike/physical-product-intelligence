import io
import json
import os
import selectors
import signal
import subprocess
import sys
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from billing.models import AccessGrant, GatewayCall, MoneyEvent, PaymentOperation
from billing.tests import Fixture
from operations.billing_processor import cycle


@override_settings(BILLING_SIMULATOR_ENABLED=True)
class BillingProcessorTests(Fixture, TransactionTestCase):
    def setUp(self):
        self.setup_billing()

    def test_verified_settlement_is_idempotent_without_new_payment_creation(self):
        item = self.ready()
        self.receipt(item)
        with patch("billing.adapter.create", side_effect=AssertionError("Never resubmit")):
            first = cycle(self.owner)
            second = cycle(self.owner)
        self.assertGreaterEqual(first["events"], 1)
        self.assertEqual(second["events"], 0)
        self.assertEqual(first["failures"], 0)
        self.assertEqual(MoneyEvent.objects.count(), 1)
        self.assertEqual(AccessGrant.objects.count(), 1)
        self.assertEqual(GatewayCall.objects.filter(action="create").count(), 1)

    def test_pending_is_never_submitted_and_expiration_uses_lookup_only(self):
        item = self.operation()
        self.assertEqual(cycle(self.owner)["lookups"], 0)
        with patch(
            "operations.billing_processor.timezone.now",
            return_value=item.expires_at + timedelta(seconds=1),
        ):
            self.assertEqual(cycle(self.owner)["lookups"], 1)
        item.refresh_from_db()
        self.assertEqual(item.state, "expired")
        self.assertFalse(GatewayCall.objects.filter(action="create").exists())

    def test_lookups_have_durable_cooldown_and_disabled_provider_is_inert(self):
        item = self.ready()
        first = cycle(self.owner)
        second = cycle(self.owner)
        self.assertEqual((first["lookups"], second["lookups"]), (1, 0))
        item.refresh_from_db()
        self.assertGreater(item.next_check_at, timezone.now())
        with (
            override_settings(BILLING_SIMULATOR_ENABLED=False),
            patch("billing.adapter.lookup", side_effect=AssertionError("No provider")),
        ):
            self.assertEqual(cycle(self.owner)["unavailable"], 1)
        self.assertFalse(MoneyEvent.objects.exists())

    def test_active_processing_lease_is_not_taken_over(self):
        import uuid

        item = self.ready()
        PaymentOperation.objects.filter(pk=item.pk).update(
            state="processing", lease=uuid.uuid4(), leased_at=timezone.now()
        )
        self.assertEqual(cycle(self.owner)["lookups"], 0)
        PaymentOperation.objects.filter(pk=item.pk).update(
            leased_at=timezone.now() - timedelta(seconds=100)
        )
        self.assertEqual(cycle(self.owner)["lookups"], 1)
        item.refresh_from_db()
        self.assertEqual(item.state, "ready")
        self.assertEqual(GatewayCall.objects.filter(action="create").count(), 1)

    def test_explicitly_enabled_command_processes_and_default_stays_disabled(self):
        item = self.ready()
        self.receipt(item)
        output = io.StringIO()
        call_command("run_billing_processor", actor=self.owner.username, once=True, stdout=output)
        self.assertEqual(json.loads(output.getvalue())["billing_cycle"]["unavailable"], 1)
        self.assertFalse(MoneyEvent.objects.exists())
        output = io.StringIO()
        call_command(
            "run_billing_processor",
            actor=self.owner.username,
            enabled=True,
            once=True,
            stdout=output,
        )
        self.assertGreaterEqual(json.loads(output.getvalue())["billing_cycle"]["events"], 1)
        self.assertEqual(MoneyEvent.objects.count(), 1)

    def test_one_failure_does_not_erase_retry_state_or_expose_provider_text(self):
        item = self.ready()
        with patch(
            "billing.services.reconcile_operation",
            side_effect=RuntimeError("private-provider-content"),
        ):
            result = cycle(self.owner)
        self.assertEqual(result["failures"], 1)
        item.refresh_from_db()
        self.assertEqual(item.state, "ready")
        self.assertGreater(item.next_check_at, timezone.now())
        self.assertNotIn("private", str(result))

    def test_enabled_daemon_settles_automatically_and_restart_does_not_duplicate(self):
        item = self.ready()
        self.receipt(item)
        env = {
            **os.environ,
            "POSTGRES_DB": connection.settings_dict["NAME"],
            "PPI_PROCESSOR_ACTOR": self.owner.username,
        }
        code = (
            "import django; django.setup(); "
            "from django.conf import settings; settings.BILLING_SIMULATOR_ENABLED=True; "
            "from django.core.management import call_command; "
            "call_command('run_billing_processor', enabled=True, interval=1)"
        )
        for attempt in range(2):
            process = subprocess.Popen(
                [sys.executable, "-u", "-c", code],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    self.assertTrue(
                        selector.select(timeout=20), "Billing daemon did not report a cycle"
                    )
                report = json.loads(process.stdout.readline())["billing_cycle"]
                self.assertEqual(report["failures"], 0)
                self.assertEqual(report["unavailable"], 0)
                if attempt == 0:
                    self.assertGreaterEqual(report["events"], 1)
                else:
                    self.assertEqual(report["events"], 0)
                process.send_signal(signal.SIGTERM)
                process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0)
                self.assertEqual(MoneyEvent.objects.count(), 1)
                self.assertEqual(GatewayCall.objects.filter(action="create").count(), 1)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)
