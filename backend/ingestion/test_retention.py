from datetime import timedelta
from unittest.mock import patch

from django.core.files.storage import storages
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from products.services import Conflict

from . import retention, services
from .models import ImportJob, ImportRow, RetentionPolicy, ReviewRecord, SourceRemoval
from .storage import read_upload
from .tests import ImportFixture, file


@override_settings(INGESTION_ALLOW_UNSCANNED=True, INGESTION_SCANNER="")
class RetentionTests(ImportFixture, TransactionTestCase):
    def setUp(self):
        self.setup_fixture()
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        self.job = services.upload(self.owner, self.org.pk, file())
        self.job = services.cancel(
            self.owner, self.org.pk, self.job.pk, {"expected_version": self.job.version}
        )
        ImportJob.objects.filter(pk=self.job.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        self.job.refresh_from_db()

    def policy(self, **changes):
        return retention.set_policy(
            self.owner,
            self.org.pk,
            expected_version=retention.policy_data(self.org)["version"],
            minimum_days=changes.get("minimum_days", 1),
            legal_hold=changes.get("legal_hold", False),
            reason="Synthetic retention policy",
        )

    def request(self):
        return retention.request_removal(
            self.owner,
            self.org.pk,
            self.job.pk,
            expected_version=self.job.version,
            reason="Synthetic unused source cleanup",
        )

    def test_default_hold_age_and_role_are_enforced(self):
        self.assertEqual(
            retention.policy_data(self.org),
            {"version": 0, "minimum_days": None, "legal_hold": True},
        )
        with self.assertRaises(Conflict):
            self.request()
        self.policy(legal_hold=True)
        with self.assertRaises(Conflict):
            self.request()
        self.policy(minimum_days=20)
        with self.assertRaises(Conflict):
            self.request()
        self.policy()
        with self.assertRaises(PermissionDenied):
            retention.request_removal(
                self.member,
                self.org.pk,
                self.job.pk,
                expected_version=self.job.version,
                reason="Denied member removal",
            )
        with self.assertRaises(NotFound):
            retention.request_removal(
                self.other,
                self.org.pk,
                self.job.pk,
                expected_version=self.job.version,
                reason="Denied foreign removal",
            )
        self.assertTrue(storages["ingestion"].exists(self.job.storage_key))

    def test_explicit_removal_preserves_source_and_history_and_is_idempotent(self):
        self.policy()
        item = self.request()
        self.assertEqual(self.request().pk, item.pk)
        self.assertTrue(read_upload(self.job))
        before = (self.job.sha256, self.job.version, self.job.size)
        self.assertTrue(retention.process_one(self.owner, item.pk))
        self.assertFalse(retention.process_one(self.owner, item.pk))
        item.refresh_from_db()
        self.job.refresh_from_db()
        self.assertEqual(item.state, "removed")
        self.assertFalse(storages["ingestion"].exists(self.job.storage_key))
        from operations.recovery import retained_sources

        retained, removed = retained_sources()
        self.assertFalse(retained.filter(pk=self.job.pk).exists())
        self.assertEqual(
            removed,
            [
                {
                    "id": str(self.job.pk),
                    "storage_key": self.job.storage_key,
                    "sha256": self.job.sha256,
                    "size": self.job.size,
                }
            ],
        )
        self.assertEqual((self.job.sha256, self.job.version, self.job.size), before)
        self.assertEqual(
            ReviewRecord.objects.filter(job=self.job, action__startswith="retention_").count(), 3
        )
        with self.assertRaises(Conflict):
            read_upload(self.job)

    def test_new_hold_or_owner_revocation_cancels_queued_request(self):
        self.policy()
        item = self.request()
        self.policy(legal_hold=True)
        self.assertFalse(retention.process_one(self.owner, item.pk))
        item.refresh_from_db()
        self.assertEqual(item.state, "cancelled")
        self.policy()
        item = self.request()
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.member.is_staff = True
        self.member.save(update_fields=["is_staff"])
        self.assertFalse(retention.process_one(self.member, item.pk))
        self.assertTrue(storages["ingestion"].exists(self.job.storage_key))

    def test_applied_evidence_and_active_family_are_never_eligible(self):
        self.policy()
        ImportJob.objects.filter(pk=self.job.pk).update(status="awaiting_review")
        self.job.refresh_from_db()
        with self.assertRaises(Conflict):
            self.request()
        ImportJob.objects.filter(pk=self.job.pk).update(status="cancelled")
        self.job.refresh_from_db()
        ImportRow.objects.create(job=self.job, number=1, location="row1", applied=True)
        with self.assertRaises(Conflict):
            self.request()

    def test_active_extraction_blocks_removal_and_claim_blocks_new_extraction(self):
        import uuid

        self.policy()

        def extraction():
            return ImportJob.objects.create(
                organization=self.org,
                created_by=self.owner,
                source_job=self.job,
                mode="ai",
                request_id=uuid.uuid4(),
                storage_key=self.job.storage_key,
                display_name=self.job.display_name,
                format=self.job.format,
                size=self.job.size,
                sha256=self.job.sha256,
                scan_status=self.job.scan_status,
            )

        active = extraction()
        with self.assertRaises(Conflict):
            self.request()
        active.status = "cancelled"
        active.save(update_fields=["status"])
        item = self.request()
        self.assertTrue(retention.process_one(self.owner, item.pk))
        with self.assertRaises(IntegrityError), transaction.atomic():
            extraction()

    def test_tampered_file_requires_review_without_removing_it(self):
        self.policy()
        item = self.request()
        path = retention.safe_path(self.job)
        path.write_bytes(b"tampered synthetic source")
        self.assertFalse(retention.process_one(self.owner, item.pk))
        self.assertTrue(path.exists())
        item.refresh_from_db()
        self.assertEqual(item.state, "needs_review")
        with self.assertRaises(ValidationError):
            retention.reconcile(self.owner, item.pk, reason="Cannot confirm changed source")
        self.assertEqual(SourceRemoval.objects.get(pk=item.pk).state, "needs_review")

    def test_recovered_claim_fences_a_worker_delayed_in_storage_verification(self):
        self.policy()
        item = self.request()
        original = retention.verified_file

        def recovered(source):
            path = original(source)
            SourceRemoval.objects.filter(pk=item.pk).update(
                state="needs_review", finished_at=timezone.now()
            )
            return path

        with patch("ingestion.retention.verified_file", side_effect=recovered):
            self.assertFalse(retention.process_one(self.owner, item.pk))
        item.refresh_from_db()
        self.assertEqual(item.state, "needs_review")
        self.assertTrue(retention.safe_path(self.job).exists())

    def test_integrity_failure_and_missing_file_require_review_never_automatic_retry(self):
        self.policy()
        item = self.request()
        with patch(
            "ingestion.retention.os.unlink", side_effect=OSError("private filesystem detail")
        ):
            self.assertFalse(retention.process_one(self.owner, item.pk))
        item.refresh_from_db()
        self.assertEqual(item.state, "needs_review")
        with self.assertRaises(Conflict):
            self.policy(legal_hold=True)
        self.assertFalse(retention.process_one(self.owner, item.pk))
        retention.reconcile(self.owner, item.pk, reason="Confirmed original file still intact")
        item.refresh_from_db()
        self.assertEqual(item.state, "cancelled")
        self.assertTrue(read_upload(self.job))
        item = self.request()
        storages["ingestion"].delete(self.job.storage_key)
        self.assertFalse(retention.process_one(self.owner, item.pk))
        item.refresh_from_db()
        self.assertEqual(item.state, "needs_review")
        retention.reconcile(
            self.owner, item.pk, reason="Confirmed file absent after interrupted operation"
        )
        item.refresh_from_db()
        self.assertEqual(item.state, "removed")
        self.policy(legal_hold=True)

    def test_hold_cannot_be_confirmed_between_durable_claim_and_unlink(self):
        self.policy()
        item = self.request()
        original = retention.verified_file

        def verify(source):
            with self.assertRaises(Conflict):
                self.policy(legal_hold=True)
            with self.assertRaises(Conflict):
                read_upload(source)
            return original(source)

        with patch("ingestion.retention.verified_file", side_effect=verify):
            self.assertTrue(retention.process_one(self.owner, item.pk))

    def test_database_history_and_transition_guards(self):
        self.policy()
        item = self.request()
        for query, changes in [
            (RetentionPolicy.objects.all(), {"legal_hold": True}),
            (SourceRemoval.objects.filter(pk=item.pk), {"sha256": "0" * 64}),
            (SourceRemoval.objects.filter(pk=item.pk), {"state": "removed"}),
        ]:
            with self.assertRaises((ValueError, IntegrityError)), transaction.atomic():
                query.update(**changes)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SourceRemoval.objects.filter(pk=item.pk).delete()

    def test_api_scope_policy_and_source_disposal(self):
        url = self.base + "retention-policy/"
        self.assertTrue(self.client.get(url).json()["legal_hold"])
        payload = {
            "expected_version": 0,
            "minimum_days": 1,
            "legal_hold": False,
            "reason": "Synthetic API retention",
        }
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.put(url, payload, format="json").status_code, 403)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.put(url, payload, format="json").status_code, 200)
        self.assertEqual(self.client.put(url, payload, format="json").status_code, 409)
        target = self.base + str(self.job.pk) + "/source-removal/"
        response = self.client.post(
            target,
            {"expected_version": self.job.version, "reason": "Synthetic API source removal"},
            format="json",
        )
        self.assertEqual(response.status_code, 202)
        self.assertNotIn("storage_key", response.json())
        self.assertEqual(retention.cycle(self.owner)["removed"], 1)
        self.assertEqual(self.client.get(self.base + str(self.job.pk) + "/file/").status_code, 409)
        self.assertEqual(
            self.client.get(self.base + str(self.job.pk) + "/").json()["source_file_state"],
            "removed",
        )
