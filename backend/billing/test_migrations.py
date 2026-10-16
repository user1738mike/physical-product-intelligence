"""Upgrade only an isolated PostgreSQL test database, preserving Phase 9A domain history."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class UpgradePreservationTests(TransactionTestCase):
    def test_phase9a_upgrade_adds_unconfigured_accounts_without_charges_or_access_changes(self):
        self.assertTrue(connection.settings_dict["NAME"].startswith("test_"))
        executor = MigrationExecutor(connection)
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
            MigrationExecutor(connection).migrate([("billing", "0002_integrity_and_backfill")])
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
            MigrationExecutor(connection).migrate([("billing", "0002_integrity_and_backfill")])
