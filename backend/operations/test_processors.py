import io
import json
import os
import selectors
import signal
import subprocess
import sys
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from compatibility import services as assessments
from compatibility.tests import Fixture
from ingestion.models import ImportJob
from integrations import services
from integrations.models import Delivery, DeliveryAttempt
from integrations.tests import CONFIG, enable
from operations.models import RateBucket
from operations.processors import cycle


@override_settings(**CONFIG)
class ProcessorTests(Fixture, TransactionTestCase):
    def setUp(self):
        self.setup_fixture()
        enable(self)

    def delivery(self):
        services.configure_destination(
            self.owner,
            self.org.pk,
            url="https://warehouse.example/events",
            subscriptions=["assessment.completed"],
        )
        assessments.assess(self.owner, self.org.pk, self.assessment_data())
        return Delivery.objects.get()

    def test_interrupted_dispatch_recovers_without_new_event_or_usage(self):
        item = self.delivery()
        services.claim(item.pk)
        Delivery.objects.filter(pk=item.pk).update(
            lease_until=timezone.now() - timedelta(seconds=1)
        )
        with patch("integrations.transport.send", return_value=(204, None)) as send:
            first = cycle(self.owner)
            second = cycle(self.owner)
        self.assertEqual((first["deliveries"], second["deliveries"]), (1, 0))
        self.assertEqual(send.call_count, 1)
        item.refresh_from_db()
        self.assertEqual(item.state, "delivered")
        self.assertEqual(DeliveryAttempt.objects.count(), 1)

    def test_disabled_transport_preserves_pending_work_and_no_ai_or_payment_calls(self):
        item = self.delivery()
        with (
            override_settings(INTEGRATION_OUTBOUND_ENABLED=False),
            patch("integrations.transport.send", side_effect=AssertionError("network")),
            patch("ingestion.ai_services.process", side_effect=AssertionError("AI")),
            patch("billing.services.process_outbound", side_effect=AssertionError("payment")),
        ):
            self.assertEqual(cycle(self.owner)["deliveries"], 0)
        item.refresh_from_db()
        self.assertEqual(item.state, "pending")

    def test_recovery_fences_stale_job_and_preserves_recent_job_and_private_file(self):
        source = ImportJob.objects.create(
            organization=self.org,
            created_by=self.owner,
            storage_key="not-read-by-recovery",
            display_name="source.txt",
            format="txt",
            size=10,
            sha256="a" * 64,
        )
        fields = dict(
            organization=self.org,
            created_by=self.owner,
            source_job=source,
            mode="ai",
            storage_key=source.storage_key,
            display_name=source.display_name,
            format="txt",
            size=10,
            sha256=source.sha256,
            status="processing",
            extraction={"lease": "expired-fence", "attempts": 1},
        )
        old = ImportJob.objects.create(
            **fields,
            request_id=uuid.uuid4(),
            started_at=timezone.now() - timedelta(seconds=100),
        )
        recent = ImportJob.objects.create(
            **fields, request_id=uuid.uuid4(), started_at=timezone.now()
        )
        RateBucket.objects.create(
            key="expired", expires_at=timezone.now() - timedelta(seconds=1), window_start=0
        )
        RateBucket.objects.create(
            key="current", expires_at=timezone.now() + timedelta(seconds=60), window_start=0
        )
        result = cycle(self.owner)
        old.refresh_from_db()
        recent.refresh_from_db()
        self.assertEqual((result["recovered"], result["counters"]), (1, 1))
        self.assertEqual((old.status, old.extraction["lease"]), ("failed", ""))
        self.assertEqual(recent.status, "processing")
        self.assertEqual(old.storage_key, source.storage_key)
        self.assertTrue(RateBucket.objects.filter(pk="current").exists())

    def test_live_operator_revocation_and_command_redaction(self):
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied):
            cycle(self.owner)
        with self.assertRaisesMessage(CommandError, "private diagnostics suppressed"):
            call_command("run_processors", actor=self.owner.username, once=True)
        self.owner.is_active = True
        self.owner.save(update_fields=["is_active"])
        output = io.StringIO()
        call_command("run_processors", actor=self.owner.username, once=True, stdout=output)
        self.assertEqual(json.loads(output.getvalue())["processor_cycle"]["failures"], 0)

    def test_failure_in_one_delivery_does_not_stop_recovery(self):
        self.delivery()
        with patch("integrations.services.dispatch_one", side_effect=RuntimeError("secret")):
            result = cycle(self.owner)
        self.assertEqual(result["failures"], 1)
        self.assertNotIn("secret", str(result))

    def test_operator_revocation_stops_later_items_in_the_same_cycle(self):
        self.delivery()
        assessments.assess(self.owner, self.org.pk, self.assessment_data())
        worker = get_user_model().objects.create_user("revoked-worker", is_staff=True)

        def sender(*args):
            get_user_model().objects.filter(pk=worker.pk).update(is_active=False)
            return 204, None

        with patch("integrations.transport.send", side_effect=sender) as send:
            with self.assertRaises(PermissionDenied):
                cycle(worker)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(Delivery.objects.filter(state="delivered").count(), 1)

    def test_real_daemon_restarts_and_stops_cleanly(self):
        env = {
            **os.environ,
            "POSTGRES_DB": connection.settings_dict["NAME"],
            "PYTHONUNBUFFERED": "1",
        }
        for _ in range(2):
            process = subprocess.Popen(
                [
                    sys.executable,
                    "manage.py",
                    "run_processors",
                    "--actor",
                    self.owner.username,
                    "--interval",
                    "1",
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    self.assertTrue(selector.select(timeout=15), "Daemon did not report a cycle")
                report = json.loads(process.stdout.readline())
                self.assertEqual(report["processor_cycle"]["failures"], 0)
                process.send_signal(signal.SIGTERM)
                process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)
