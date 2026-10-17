"""Upgrade only an isolated PostgreSQL test database, preserving Phase 9A domain history."""

import uuid
from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from billing.tests import Fixture


class UpgradePreservationTests(TransactionTestCase):
    def test_phase9a_upgrade_adds_unconfigured_accounts_without_charges_or_access_changes(self):
        self.assertTrue(connection.settings_dict["NAME"].startswith("test_"))
        executor = MigrationExecutor(connection)
        current = executor.loader.graph.leaf_nodes()
        executor.migrate([("billing", None)])
        try:
            previous = (
                MigrationExecutor(connection)
                .loader.project_state(
                    [
                        ("commercial", "0006_operator_history_guard"),
                        ("products", "0004_finite_physical_values"),
                    ]
                )
                .apps
            )
            Org = previous.get_model("organizations", "Organization")
            Plan = previous.get_model("commercial", "Plan")
            Account = previous.get_model("commercial", "Account")
            Assignment = previous.get_model("commercial", "Assignment")
            Product = previous.get_model("products", "Product")
            org = Org.objects.create(name="Pre-billing fixture", slug="pre-billing-fixture")
            plan, _ = Plan.objects.get_or_create(
                code="manual-pilot", version=1, defaults={"name": "Manual pilot"}
            )
            account = Account.objects.create(organization=org)
            assignment = Assignment.objects.create(
                organization=org,
                plan=plan,
                starts_at=timezone.now(),
                reason="Existing manual access",
            )
            product = Product.objects.create(organization=org, sku="PRE-BILLING")
            start = account.metering_started_at
            MigrationExecutor(connection).migrate(current)
            from billing.models import BillingAccount, MoneyEvent, Price, Statement
            from commercial.models import Account as CurrentAccount
            from commercial.models import Assignment as CurrentAssignment
            from commercial.models import Usage
            from products.models import Product as CurrentProduct

            billing = BillingAccount.objects.get(organization_id=org.pk)
            self.assertEqual(
                (billing.provider, billing.merchant, billing.customer_ref), ("", "", "")
            )
            self.assertEqual(CurrentAssignment.objects.get(pk=assignment.pk).plan_id, plan.pk)
            self.assertEqual(
                CurrentAccount.objects.get(organization_id=org.pk).metering_started_at, start
            )
            self.assertEqual(CurrentProduct.objects.get(pk=product.pk).sku, "PRE-BILLING")
            self.assertFalse(MoneyEvent.objects.exists())
            self.assertFalse(Statement.objects.exists())
            self.assertFalse(Price.objects.exists())
            self.assertFalse(Usage.objects.exists())
        finally:
            MigrationExecutor(connection).migrate(current)


@override_settings(BILLING_SIMULATOR_ENABLED=True)
class SchedulingUpgradePreservationTests(Fixture, TransactionTestCase):
    def test_scheduling_upgrade_preserves_existing_operation_and_verified_inbox(self):
        from billing import services
        from billing.models import Inbox, MoneyEvent, PaymentOperation

        self.assertTrue(connection.settings_dict["NAME"].startswith("test_"))
        self.setup_billing()
        operation = self.ready()
        event, _, _, _ = self.receipt(operation)
        before = (operation.amount_minor, operation.fingerprint, event.raw_sha256, event.payload)
        executor = MigrationExecutor(connection)
        current = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([("billing", "0002_integrity_and_backfill")])
            old = (
                MigrationExecutor(connection)
                .loader.project_state([("billing", "0002_integrity_and_backfill")])
                .apps.get_model("billing", "PaymentOperation")
                .objects.get(pk=operation.pk)
            )
            self.assertEqual(old.amount_minor, operation.amount_minor)
            MigrationExecutor(connection).migrate(current)
            operation = PaymentOperation.objects.get(pk=operation.pk)
            event = Inbox.objects.get(pk=event.pk)
            self.assertEqual(
                (operation.amount_minor, operation.fingerprint, event.raw_sha256, event.payload),
                before,
            )
            self.assertIsNotNone(operation.next_check_at)
            self.assertIsNotNone(event.next_check_at)
            self.assertEqual(event.state, "received")
            self.assertFalse(MoneyEvent.objects.exists())
            # A rolled-back application omits the new column. A retained DB
            # default, rather than only an ORM default, must keep that write valid.
            statement = services.generate(
                self.outsider,
                self.foreign_account,
                self.price,
                start=self.statement.period_start,
                end=self.statement.period_end,
                reason="Synthetic old-writer compatibility",
            )
            statement = services.finalize(self.outsider, statement, reason="Synthetic old writer")
            legacy = old.__class__.objects.create(
                account_id=self.foreign_account.pk,
                statement_id=statement.pk,
                principal_id=self.outsider.pk,
                request_id=uuid.uuid4(),
                fingerprint="b" * 64,
                provider="simulator",
                merchant=self.foreign_account.merchant,
                mode="test",
                currency="XTS",
                amount_minor=1000,
                expires_at=timezone.now() + timedelta(minutes=15),
            )
            self.assertIsNotNone(PaymentOperation.objects.get(pk=legacy.pk).next_check_at)
        finally:
            MigrationExecutor(connection).migrate(current)
