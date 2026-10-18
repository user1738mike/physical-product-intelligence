import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import DatabaseError, close_old_connections, connection, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from compatibility import services as assessments
from compatibility.tests import Fixture as AssessmentFixture
from ingestion import ai_provider, ai_services
from ingestion.test_ai import Fixture as ExtractionFixture
from ingestion.test_ai import item
from ingestion.tests import ImportFixture, file
from organizations import services as tenants
from organizations.models import Membership
from products import services as catalog
from products.models import Product

from . import services
from .models import Account, Assignment, AssignmentEvent, Plan, Reservation, ReservationEvent, Usage


class Fixture:
    def setup_commercial(self):
        self.actor = get_user_model().objects.create_user("commercial-operator", is_staff=True)
        self.org = tenants.create_organization(
            self.actor, name="Commercial fixture", slug="commercial-fixture"
        )

    def assign(self, **policy):
        values = {key: value for key, value in services.PILOT.items() if key != "name"}
        plan = services.publish(
            self.actor,
            code="synthetic",
            version=Plan.objects.filter(code="synthetic").count() + 1,
            name="Synthetic finite fixture",
            policy={**values, **policy},
        )
        return services.assign(self.actor, self.org, plan, reason="Synthetic test assignment")

    def reserve(self, operation=None, **kwargs):
        return services.reserve(
            self.org, "extractions", operation or uuid.uuid4(), "a" * 64, **kwargs
        )

    def product(self, sku="NEW"):
        return catalog.create_product(
            self.actor,
            self.org.pk,
            {"sku": sku, "revision": {"name": "Synthetic product", "change_reason": "Fixture"}},
        )


class PolicyTests(Fixture, TestCase):
    def setUp(self):
        self.setup_commercial()

    def test_atomic_idempotent_pilot_enrollment_and_no_fabricated_usage(self):
        services.enroll(self.org, self.actor)
        self.assertEqual(Assignment.objects.filter(organization=self.org).count(), 1)
        self.assertTrue(Account.objects.filter(organization=self.org).exists())
        self.assertEqual(Usage.objects.count(), 0)
        self.assertIsNone(services.current(self.org).plan.active_products_limit)
        with patch("organizations.services.record", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                tenants.create_organization(self.actor, name="Rollback", slug="rollback")
        self.assertFalse(Account.objects.filter(organization__slug="rollback").exists())

    def test_policy_rejects_unknown_boolean_integer_and_negative_limits(self):
        values = {k: v for k, v in services.PILOT.items() if k != "name"}
        for changes in (
            {"unknown": True},
            {"ai_extraction": 1},
            {"assessments_limit": True},
            {"extractions_limit": -1},
            {"active_products_limit": "unlimited"},
        ):
            with self.assertRaises(ValidationError):
                services.publish(
                    self.actor, code="bad", version=1, name="Bad", policy={**values, **changes}
                )

    def test_plan_immutable_in_orm_and_raw_sql(self):
        plan = services.current(self.org).plan
        with self.assertRaises(ValueError):
            plan.save()
        with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE commercial_plan SET name='changed' WHERE id=%s", [plan.pk])

    def test_database_excludes_overlapping_assignments_and_invalid_periods(self):
        old = services.current(self.org)
        with self.assertRaises(DatabaseError), transaction.atomic():
            Assignment.objects.create(
                organization=self.org, plan=old.plan, starts_at=timezone.now(), reason="Overlap"
            )
        with self.assertRaises(DatabaseError), transaction.atomic():
            Assignment.objects.create(
                organization=self.org,
                plan=old.plan,
                starts_at=timezone.now(),
                ends_at=old.starts_at,
                reason="Invalid",
            )

    def test_zero_unlimited_disabled_and_missing_policy_fail_closed(self):
        self.assign(active_products_limit=0, extractions_limit=0, assessments=False)
        with self.assertRaises(services.Restricted):
            self.product()
        with self.assertRaises(services.Restricted):
            self.reserve()
        with transaction.atomic(), self.assertRaises(services.Restricted):
            services.require(self.org, "assessments")
        self.assign()
        self.product()
        with self.assertRaises(ValueError), transaction.atomic():
            services.require(self.org, "unknown")
        with patch("commercial.services.current", return_value=None):
            with self.assertRaises(services.Restricted):
                self.product("NO-POLICY")

    def test_expiry_suspension_and_scheduled_replacement_are_evaluated_on_read(self):
        assignment = self.assign()
        services.transition(self.actor, self.org, assignment.pk, action="suspend", reason="Fixture")
        with self.assertRaises(services.Restricted):
            self.product()
        self.assertEqual(services.summary(self.actor, self.org.pk)["status"], "suspended")
        services.transition(self.actor, self.org, assignment.pk, action="resume", reason="Fixture")
        end = timezone.now() + timedelta(minutes=1)
        services.transition(
            self.actor,
            self.org,
            assignment.pk,
            action="expire",
            reason="Scheduled end",
            ends_at=end,
        )
        with patch("commercial.services.timezone.now", return_value=end):
            self.assertIsNone(services.current(self.org))
            self.assertEqual(services.summary(self.actor, self.org.pk)["status"], "expired")
        self.assertGreaterEqual(AssignmentEvent.objects.count(), 5)

    def test_scheduled_assignment_starts_exactly_at_boundary(self):
        future = timezone.now() + timedelta(days=1)
        old = services.current(self.org)
        new = services.assign(self.actor, self.org, old.plan, reason="Scheduled", starts_at=future)
        self.assertEqual(services.current(self.org).pk, old.pk)
        self.assertEqual(services.current(self.org, at=future).pk, new.pk)

    def test_capacity_archival_reactivation_and_rollback(self):
        self.assign(active_products_limit=1)
        product = self.product()
        with self.assertRaises(services.Restricted):
            self.product("OVER")
        catalog.set_product_active(self.actor, self.org.pk, product.pk, {"is_active": False})
        second = self.product("SECOND")
        with self.assertRaises(services.Restricted):
            catalog.set_product_active(self.actor, self.org.pk, product.pk, {"is_active": True})
        assignment = services.current(self.org)
        services.transition(
            self.actor, self.org, assignment.pk, action="suspend", reason="Read only"
        )
        catalog.set_product_active(self.actor, self.org.pk, second.pk, {"is_active": False})
        self.assertEqual(Product.objects.filter(organization=self.org, is_active=True).count(), 0)

    def test_usage_reservations_duplicates_adjustments_and_replacement_do_not_reset(self):
        self.assign(extractions_limit=1)
        reservation = self.reserve()
        self.assertEqual(self.reserve(reservation.operation).pk, reservation.pk)
        with self.assertRaises(services.Restricted):
            self.reserve()
        services.finalize(self.org, "extractions", reservation.operation, self.actor)
        services.finalize(self.org, "extractions", reservation.operation, self.actor)
        self.assertEqual(Usage.objects.count(), 1)
        self.assign(extractions_limit=1)
        with self.assertRaises(services.Restricted):
            self.reserve()
        usage = Usage.objects.get()
        operation = uuid.uuid4()
        adjustment = services.adjust(
            self.actor,
            self.org,
            usage.pk,
            amount=-1,
            operation=operation,
            reason="Correct synthetic outcome",
        )
        self.assertEqual(
            services.adjust(
                self.actor,
                self.org,
                usage.pk,
                amount=-1,
                operation=operation,
                reason="Correct synthetic outcome",
            ).pk,
            adjustment.pk,
        )
        with self.assertRaises(ValidationError):
            services.adjust(
                self.actor,
                self.org,
                usage.pk,
                amount=-1,
                operation=uuid.uuid4(),
                reason="Negative total",
            )
        self.reserve()
        self.assertGreaterEqual(ReservationEvent.objects.count(), 3)

    def test_request_identity_input_conflict_and_wrong_worker_fence(self):
        r = self.reserve(fence="first")
        with self.assertRaises(services.Restricted):
            services.reserve(self.org, "extractions", r.operation, "b" * 64)
        with self.assertRaises(services.Restricted):
            services.finalize(self.org, "extractions", r.operation, self.actor, fence="late")
        services.release(self.org, r.operation)
        r = self.reserve(r.operation, fence="new")
        with self.assertRaises(services.Restricted):
            services.finalize(self.org, "extractions", r.operation, self.actor, fence="first")
        services.finalize(self.org, "extractions", r.operation, self.actor, fence="new")
        self.assertEqual(Usage.objects.count(), 1)

    def test_pinned_utc_month_and_transaction_rollback(self):
        before = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
        r = self.reserve(at=before)
        with patch(
            "commercial.services.timezone.now", return_value=datetime(2027, 1, 1, tzinfo=UTC)
        ):
            services.finalize(self.org, "extractions", r.operation, self.actor)
        self.assertEqual(Usage.objects.get().period_end, datetime(2027, 1, 1, tzinfo=UTC))
        self.assertEqual(
            services.month(datetime(2027, 1, 1, tzinfo=UTC))[0], datetime(2027, 1, 1, tzinfo=UTC)
        )
        with self.assertRaises(RuntimeError), transaction.atomic():
            r = self.reserve()
            services.finalize(self.org, "extractions", r.operation, self.actor)
            raise RuntimeError()
        self.assertEqual(Usage.objects.count(), 1)

    def test_owner_admin_member_foreign_revoked_and_no_customer_mutations(self):
        member = get_user_model().objects.create_user("commercial-member")
        membership = Membership.objects.create(organization=self.org, user=member, role="member")
        client = APIClient()
        path = f"/api/v1/organizations/{self.org.pk}/commercial/"
        client.force_authenticate(member)
        self.assertEqual(client.get(path).status_code, 403)
        membership.role = "admin"
        membership.save()
        self.assertEqual(client.get(path).status_code, 200)
        response = client.get(path)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotIn("reason", str(response.data["history"]))
        self.assertEqual(client.post(path, {}, format="json").status_code, 405)
        membership.delete()
        self.assertEqual(client.get(path).status_code, 404)
        member.is_staff = True
        member.save()
        self.assertEqual(client.get(path).status_code, 404)
        client.force_authenticate(self.actor)
        self.assertEqual(client.get(path).status_code, 200)

    def test_runtime_role_cannot_grant_plans_rewrite_usage_or_run_operator(self):
        reservation = self.reserve()
        services.finalize(self.org, "extractions", reservation.operation, self.actor)
        role = connection.ops.quote_name("ppi_phase9_test_" + uuid.uuid4().hex[:12])
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {role} NOLOGIN NOINHERIT")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            cursor.execute(
                f"GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {role}"
            )
            cursor.execute(f"GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
            cursor.execute(f"SET LOCAL ROLE {role}")
        try:
            self.product()
            with self.assertRaises(PermissionDenied):
                services.operator(self.actor)
            for sql in (
                "UPDATE commercial_assignment SET status='suspended'",
                "DELETE FROM commercial_usage",
                "UPDATE commercial_account SET metering_started_at=now()",
                "UPDATE commercial_reservation SET state='reserved'",
            ):
                with (
                    self.assertRaises(DatabaseError),
                    transaction.atomic(),
                    connection.cursor() as cursor,
                ):
                    cursor.execute(sql)
            new_org = tenants.create_organization(
                self.actor, name="Runtime enrollment", slug="runtime-enrollment"
            )
            self.assertIsNotNone(services.current(new_org))
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def test_reconcile_audited_read_only_and_command_rejects_unprivileged_actor(self):
        output = io.StringIO()
        call_command(
            "commercial",
            "reconcile",
            actor=self.actor.username,
            organization=str(self.org.pk),
            reason="Fixture reconciliation",
            stdout=output,
        )
        self.assertIn('"history_rewritten": false', output.getvalue())
        self.assertEqual(Usage.objects.count(), 0)
        self.actor.is_staff = False
        self.actor.save()
        with self.assertRaises(PermissionDenied):
            services.operator(self.actor)

    def test_backfill_is_idempotent_and_preserves_existing_assignment(self):
        import importlib

        from django.apps import apps

        migration = importlib.import_module("commercial.migrations.0003_seed_and_guards")
        item = self.assign(extractions_limit=7)
        before = (
            Assignment.objects.count(),
            Account.objects.count(),
            AssignmentEvent.objects.count(),
        )
        migration.seed(apps, None)
        migration.seed(apps, None)
        self.assertEqual(
            before,
            (Assignment.objects.count(), Account.objects.count(), AssignmentEvent.objects.count()),
        )
        self.assertEqual(services.current(self.org).pk, item.pk)

    def test_database_rejects_cross_tenant_usage_and_unpaired_finalization(self):
        other = tenants.create_organization(self.actor, name="Other", slug="scope-other")
        r = self.reserve()
        with self.assertRaises(DatabaseError), transaction.atomic():
            Usage.objects.create(
                organization=other,
                reservation=r,
                assignment=r.assignment,
                operation=r.operation,
                meter=r.meter,
                period_start=r.period_start,
                period_end=r.period_end,
                amount=1,
                actor=self.actor,
                reason="Invalid scope",
            )
        with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE commercial_reservation SET state='finalized' WHERE id=%s", [r.pk]
            )
            cursor.execute("SET CONSTRAINTS ppi_reservation_finalized IMMEDIATE")
        with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            Usage.objects.create(
                organization=self.org,
                reservation=r,
                assignment=r.assignment,
                operation=r.operation,
                meter=r.meter,
                period_start=r.period_start,
                period_end=r.period_end,
                amount=1,
                actor=self.actor,
                reason="Unpaired completion",
            )
            cursor.execute("SET CONSTRAINTS ppi_usage_finalized IMMEDIATE")


class ImportCapacityTests(ImportFixture, Fixture, TestCase):
    def setUp(self):
        self.setup_fixture()
        self.actor = self.owner
        self.actor.is_staff = True
        self.actor.save()

    def test_bulk_import_cap_rolls_back_all_products_and_remains_retryable(self):
        from ingestion import services as ingestion

        self.assign(active_products_limit=1)
        job = self.prepared(file(b"sku,name\nA,First\nB,Second\n"))
        job = self.approve(job)
        with self.assertRaises(services.Restricted):
            ingestion.apply(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        self.assertEqual(Product.objects.filter(organization=self.org).count(), 0)
        job.refresh_from_db()
        self.assertEqual(job.status, "awaiting_review")
        self.assertEqual(Usage.objects.filter(meter="extractions").count(), 1)
        self.assign(active_products_limit=2)
        job = ingestion.apply(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        self.assertEqual(Product.objects.filter(organization=self.org).count(), 2)
        ingestion.apply(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        self.assertEqual(Usage.objects.filter(meter="extractions").count(), 1)

    def test_disabled_imports_and_zero_extraction_quota_before_processing(self):
        from ingestion import services as ingestion

        self.assign(evidence_import=False)
        with self.assertRaises(services.Restricted):
            ingestion.upload(self.owner, self.org.pk, file())
        self.assign(extractions_limit=0)
        with self.assertRaises(services.Restricted):
            self.prepared()
        self.assertFalse(Usage.objects.exists())


class AssessmentTests(AssessmentFixture, Fixture, TestCase):
    def setUp(self):
        self.setup_fixture()
        self.actor = self.owner
        self.actor.is_staff = True
        self.actor.save()
        self.activate()

    def test_one_success_duplicate_and_last_allowance_historical_read(self):
        self.assign(assessments_limit=1)
        data = self.assessment_data()
        result = assessments.assess(self.owner, self.org.pk, data)
        self.assertEqual(assessments.assess(self.owner, self.org.pk, data).pk, result.pk)
        with self.assertRaises(services.Restricted):
            assessments.assess(self.owner, self.org.pk, self.assessment_data())
        self.assertEqual(Usage.objects.filter(meter="assessments").count(), 1)
        self.assertEqual(assessments.assessment_get(self.org, result.pk).pk, result.pk)

    def test_business_failure_consumes_no_quota(self):
        self.assign(assessments_limit=1)
        with patch("compatibility.services.engine.evaluate", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                assessments.assess(self.owner, self.org.pk, self.assessment_data())
        self.assertFalse(Reservation.objects.exists())
        self.assertFalse(Usage.objects.exists())


class ExtractionTests(ExtractionFixture, Fixture, TestCase):
    def setUp(self):
        self.setup_ai()
        self.actor = self.owner
        self.actor.is_staff = True
        self.actor.save()

    def test_mocked_completion_counts_once_independent_of_candidates(self):
        self.assign(extractions_limit=1)
        job = self.run_job(items=[item(), item("2", "kg")])
        self.assertEqual(job.status, "awaiting_review")
        self.assertEqual(Usage.objects.filter(meter="extractions").count(), 1)
        self.run_job(job)
        self.assertEqual(Usage.objects.count(), 1)
        with self.assertRaises(services.Restricted):
            self.run_job()

    def test_failure_and_cancel_release_without_usage(self):
        self.assign(extractions_limit=1)
        job = self.run_job(error=ai_provider.ProviderFailure("timeout", True))
        self.assertEqual(job.status, "failed")
        self.assertFalse(Usage.objects.exists())
        self.assertEqual(Reservation.objects.get().state, "released")
        from ingestion.services import cancel

        pending = self.start()
        pending, lease = ai_services.claim(
            self.owner, self.org.pk, pending.pk, {"expected_version": pending.version}
        )
        cancel(self.owner, self.org.pk, pending.pk, {"expected_version": pending.version})
        ai_services.finish(self.owner, self.org.pk, pending.pk, lease, [], [], {}, 1)
        self.assertFalse(Usage.objects.exists())
        self.assertEqual(Reservation.objects.filter(state="reserved").count(), 0)

    def test_abandoned_recovery_fences_original_worker(self):
        job = self.start()
        job, lease = ai_services.claim(
            self.owner, self.org.pk, job.pk, {"expected_version": job.version}
        )
        from ingestion.models import ImportJob

        ImportJob.objects.filter(pk=job.pk).update(
            started_at=timezone.now() - timedelta(seconds=91)
        )
        self.assertEqual(
            services.recover(self.actor, self.org, reason="Synthetic abandoned worker"), 1
        )
        result = ai_services.finish(self.owner, self.org.pk, job.pk, lease, [], [], {}, 1)
        self.assertEqual(result.status, "failed")
        self.assertFalse(Usage.objects.exists())


class ConcurrencyTests(Fixture, TransactionTestCase):
    def setUp(self):
        self.setup_commercial()

    def race(self, operation):
        gate = Barrier(2)

        def run(i):
            close_old_connections()
            try:
                gate.wait(timeout=15)
                operation(i)
                return "passed"
            except services.Restricted:
                return "denied"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, range(2)))

    def test_last_product_capacity_serialized(self):
        self.assign(active_products_limit=1)
        self.assertCountEqual(self.race(lambda i: self.product(str(i))), ["passed", "denied"])
        self.assertEqual(Product.objects.filter(organization=self.org).count(), 1)

    def test_last_event_allowance_serialized(self):
        self.assign(extractions_limit=1)
        self.assertCountEqual(self.race(lambda _: self.reserve()), ["passed", "denied"])
        self.assertEqual(Reservation.objects.filter(state="reserved").count(), 1)

    def test_concurrent_duplicate_completion_consumes_once(self):
        r = self.reserve()
        self.assertEqual(
            self.race(
                lambda _: services.finalize(self.org, "extractions", r.operation, self.actor)
            ),
            ["passed", "passed"],
        )
        self.assertEqual(Usage.objects.count(), 1)
