import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import DatabaseError, close_old_connections, connection, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from commercial import services as access
from commercial.models import Assignment, Usage
from organizations.models import Membership
from organizations.services import create_organization

from . import adapter, services
from .models import (
    AccessGrant,
    Allocation,
    BillingAccount,
    GatewayCall,
    GatewayObject,
    Inbox,
    MoneyEvent,
    PaymentOperation,
    Statement,
)


class Fixture:
    def setup_billing(self):
        self.assertTrue(
            adapter.enabled(),
            repr(
                (
                    settings.BILLING_SIMULATOR_ENABLED,
                    settings.SETTINGS_MODULE,
                    connection.settings_dict["NAME"],
                )
            ),
        )
        self.owner = get_user_model().objects.create_user("billing-owner", is_staff=True)
        self.outsider = get_user_model().objects.create_user("billing-outsider", is_staff=True)
        self.member = get_user_model().objects.create_user("billing-member")
        self.org = create_organization(self.owner, name="Billing fixture", slug="billing-fixture")
        self.other = create_organization(self.outsider, name="Billing other", slug="billing-other")
        Membership.objects.create(organization=self.org, user=self.member, role="member")
        self.account = services.configure_simulator(
            self.owner, self.org, reason="Synthetic fixture"
        )
        self.foreign_account = services.configure_simulator(
            self.outsider, self.other, reason="Synthetic fixture"
        )
        policy = {k: v for k, v in access.PILOT.items() if k != "name"}
        self.plan = access.publish(
            self.owner,
            code="billing-fixture",
            version=1,
            name="Synthetic billing access",
            policy={**policy, "active_products_limit": 10},
        )
        self.price = services.publish_price(
            self.owner,
            code="synthetic-price",
            version=1,
            plan=self.plan,
            currency_code="XTS",
            exponent=0,
            unit_minor=1000,
            mode="test",
            reason="Synthetic price only",
        )
        start, end = access.month()
        self.statement = services.generate(
            self.owner,
            self.account,
            self.price,
            start=start,
            end=end,
            access_transition=True,
            reason="Explicit synthetic pilot replacement",
        )
        self.statement = services.finalize(
            self.owner, self.statement, reason="Synthetic finalization"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.root = f"/api/v1/organizations/{self.org.pk}/billing/"

    def operation(self, **kwargs):
        return services.request_operation(
            self.owner, self.org.pk, self.statement.pk, uuid.uuid4(), **kwargs
        )

    def ready(self, **kwargs):
        operation = self.operation(**kwargs)
        return services.process_outbound(self.owner, operation.pk)

    def receipt(
        self,
        operation,
        *,
        kind="payment.succeeded",
        event_id=None,
        effect_id=None,
        amount=None,
        reverses="",
        changes=None,
    ):
        states = {
            "payment.succeeded": "paid",
            "payment.failed": "failed",
            "subscription.cancelled": "cancelled",
            "refund.observed": "refunded",
            "dispute.observed": "disputed",
        }
        obj = GatewayObject.objects.get(operation=operation)
        obj.version += 1
        obj.state = states.get(kind, "pending")
        if kind == "payment.succeeded" and amount is not None:
            obj.amount_minor = amount
        obj.save()
        payload = adapter.payload(
            operation,
            obj,
            kind=kind,
            event_id=event_id,
            effect_id=effect_id,
            amount=amount,
            reverses=reverses,
        )
        payload.update(changes or {})
        body = json.dumps(payload, sort_keys=True).encode()
        timestamp, proof = adapter.sign(body)
        return services.receive(body, timestamp, proof), body, timestamp, proof


@override_settings(BILLING_SIMULATOR_ENABLED=True)
class BillingTests(Fixture, TestCase):
    def setUp(self):
        self.setup_billing()

    def test_currency_exponents_integer_arithmetic_and_immutable_prices(self):
        for i, (code, exponent) in enumerate((("JPY", 0), ("KWD", 3), ("USD", 2)), 2):
            p = services.publish_price(
                self.owner,
                code="synthetic-price",
                version=i,
                plan=self.plan,
                currency_code=code,
                exponent=exponent,
                unit_minor=123,
                mode="test",
                reason="Currency capability fixture",
            )
            self.assertEqual(p.unit_minor, 123)
        for code, exponent in (("JPY", 2), ("KWD", 2), ("ZZZ", 2), ("XTS", 2)):
            with self.assertRaises(ValidationError):
                services.currency(code, exponent, "test")
        for value in (-1, 1.5, True, 10**16):
            with self.assertRaises(ValidationError):
                services.amount(value)
        with self.assertRaises(ValueError):
            self.price.save()
        with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as c:
            c.execute("UPDATE billing_price SET unit_minor=1 WHERE id=%s", [self.price.pk])

    def test_statement_period_generation_and_finalization_are_idempotent(self):
        same = services.generate(
            self.owner,
            self.account,
            self.price,
            start=self.statement.period_start,
            end=self.statement.period_end,
            access_transition=True,
            reason="Repeated generation",
        )
        self.assertEqual(same.pk, self.statement.pk)
        self.assertEqual(services.finalize(self.owner, same, reason="Repeat").pk, same.pk)
        with self.assertRaises(services.Conflict):
            services.generate(
                self.owner,
                self.account,
                self.price,
                start=self.statement.period_start,
                end=self.statement.period_end,
                quantity=2,
                reason="Conflicting period",
            )
        snapshot = dict(self.statement.snapshot)
        services.publish_price(
            self.owner,
            code=self.price.code,
            version=2,
            plan=self.plan,
            currency_code="XTS",
            exponent=0,
            unit_minor=999,
            mode="test",
            reason="New version",
        )
        self.statement.refresh_from_db()
        self.assertEqual(self.statement.snapshot, snapshot)
        with self.assertRaises(DatabaseError), transaction.atomic():
            Statement.objects.filter(pk=self.statement.pk).update(total_minor=1)

    def test_draft_revisions_and_linked_corrections(self):
        start = self.statement.period_end
        end = start + timedelta(days=30)
        draft = services.generate(
            self.owner,
            self.account,
            self.price,
            start=start,
            end=end,
            reason="Next synthetic period",
        )
        draft = services.revise(
            self.owner, draft, quantity=2, expected_version=1, reason="Reviewed draft"
        )
        self.assertEqual(draft.version, 2)
        with self.assertRaises(services.Conflict):
            services.revise(self.owner, draft, quantity=3, expected_version=1, reason="Stale")
        draft = services.finalize(self.owner, draft, reason="Reviewed")
        self.assertEqual(draft.total_minor, 2000)
        operation = uuid.uuid4()
        correction = services.adjust_statement(
            self.owner, draft, delta_minor=-100, operation=operation, reason="Explicit correction"
        )
        self.assertEqual(services.total(draft), 1900)
        self.assertEqual(
            services.adjust_statement(
                self.owner,
                draft,
                delta_minor=-100,
                operation=operation,
                reason="Explicit correction",
            ).pk,
            correction.pk,
        )
        with self.assertRaises(services.Conflict):
            services.adjust_statement(
                self.owner,
                draft,
                delta_minor=-200,
                operation=operation,
                reason="Changed correction",
            )
        with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as c:
            c.execute("DELETE FROM billing_statementadjustment")

    def test_duplicate_click_identity_and_no_access_from_status_or_redirect(self):
        key = uuid.uuid4()
        operation = services.request_operation(self.owner, self.org.pk, self.statement.pk, key)
        self.assertEqual(
            services.request_operation(self.owner, self.org.pk, self.statement.pk, key).pk,
            operation.pk,
        )
        membership = Membership.objects.get(organization=self.org, user=self.member)
        membership.role = "admin"
        membership.save()
        with self.assertRaises(services.Conflict):
            services.request_operation(self.member, self.org.pk, self.statement.pk, key)
        with self.assertRaises(services.Conflict):
            self.operation()
        self.client.get(self.root + f"?success=true&operation={operation.pk}")
        self.assertFalse(AccessGrant.objects.exists())
        self.assertFalse(MoneyEvent.objects.exists())
        self.assertEqual(access.current(self.org).plan.code, "manual-pilot")

    def test_receipt_persists_before_processing_and_duplicate_semantics(self):
        operation = self.ready()
        event, body, timestamp, proof = self.receipt(operation)
        self.assertEqual(event.state, "received")
        self.assertEqual(MoneyEvent.objects.count(), 0)
        response = self.client.post(
            "/api/v1/billing/synthetic-inbox/",
            body,
            content_type="application/json",
            HTTP_X_PPI_TEST_TIME=timestamp,
            HTTP_X_PPI_TEST_PROOF=proof,
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(Inbox.objects.count(), 1)
        result = services.process_event(self.owner, event.pk)
        self.assertEqual(result.state, "applied")
        self.assertEqual(services.settled(self.statement), 1000)
        self.assertEqual(AccessGrant.objects.count(), 1)
        self.assertEqual(access.current(self.org).plan_id, self.plan.pk)
        self.assertEqual(access.current(self.org).source, "verified_payment")

    def test_equivalent_events_do_not_apply_payment_twice(self):
        operation = self.ready()
        event, body, _, _ = self.receipt(operation)
        services.process_event(self.owner, event.pk)
        payload = json.loads(body)
        payload["event_id"] = "equivalent-delivery"
        new_body = json.dumps(payload).encode()
        t, p = adapter.sign(new_body)
        equivalent = services.receive(new_body, t, p)
        services.process_event(self.owner, equivalent.pk)
        self.assertEqual(MoneyEvent.objects.count(), 1)
        self.assertEqual(Allocation.objects.count(), 1)
        self.assertEqual(AccessGrant.objects.count(), 1)
        self.assertEqual(Assignment.objects.filter(organization=self.org).count(), 2)

    def test_unknown_submission_recovery_never_resubmits(self):
        operation = self.operation()
        original = adapter.create

        def timeout_after_submission(item):
            original(item)
            raise adapter.UnknownOutcome()

        with patch("billing.adapter.create", side_effect=timeout_after_submission):
            result = services.process_outbound(self.owner, operation.pk)
        self.assertEqual(result.state, "unknown")
        with patch("billing.adapter.create", side_effect=AssertionError("No second create")):
            services.reconcile_operation(
                self.owner, operation.pk, reason="Uncertain submission", dry_run=False
            )
            services.process_outbound(self.owner, operation.pk)
        self.assertEqual(GatewayCall.objects.filter(action="create").count(), 1)
        operation.refresh_from_db()
        self.assertEqual(operation.state, "ready")

    def test_invalid_expired_modified_and_conflicting_event_delivery(self):
        operation = self.ready()
        _, body, t, p = self.receipt(operation)
        for raw, stamp, proof in (
            (body, t, "bad"),
            (body + b" ", t, p),
            (body, str(int(t) - 301), p),
            (b"x" * 65537, t, p),
        ):
            with self.assertRaises(ValidationError):
                services.receive(raw, stamp, proof)
        changed = json.loads(body)
        changed["amount_minor"] = 2
        raw = json.dumps(changed).encode()
        stamp, proof = adapter.sign(raw)
        with self.assertRaises(services.Conflict):
            services.receive(raw, stamp, proof)
        self.assertFalse(MoneyEvent.objects.exists())

    def test_unknown_customer_foreign_object_and_live_events_cannot_grant(self):
        operation = self.ready()
        event, _, _, _ = self.receipt(operation, changes={"customer": "unknown-customer"})
        self.assertEqual(event.state, "quarantined")
        foreign, _, _, _ = self.receipt(
            operation, changes={"customer": self.foreign_account.customer_ref}
        )
        self.assertEqual(services.process_event(self.owner, foreign.pk).outcome, "unmapped_object")
        with self.assertRaises(ValidationError):
            self.receipt(operation, changes={"mode": "live"})
        self.assertFalse(AccessGrant.objects.exists())

    def test_partial_installments_and_usage_preservation(self):
        reservation = access.reserve(self.org, "extractions", uuid.uuid4(), "a" * 64)
        access.finalize(self.org, "extractions", reservation.operation, self.owner)
        first = self.ready(partial_minor=400)
        event, _, _, _ = self.receipt(first)
        services.process_event(self.owner, event.pk)
        self.assertEqual(
            services.statement_data(self.statement)["settlement_status"], "partially_settled"
        )
        self.assertEqual(AccessGrant.objects.count(), 0)
        second = self.ready()
        self.assertEqual(second.amount_minor, 600)
        event, _, _, _ = self.receipt(second)
        services.process_event(self.owner, event.pk)
        self.assertEqual(services.statement_data(self.statement)["settlement_status"], "settled")
        self.assertEqual(AccessGrant.objects.count(), 1)
        self.assertEqual(Usage.objects.filter(organization=self.org).count(), 1)

    def test_under_and_overpayment_are_quarantined_unapplied_credit(self):
        operation = self.ready()
        event, _, _, _ = self.receipt(operation, amount=900)
        done = services.process_event(self.owner, event.pk)
        self.assertEqual(done.outcome, "amount_mismatch_unapplied_credit")
        self.assertEqual(
            services.account_summary(self.owner, self.org.pk)["unapplied_credit"]["XTS"], "900"
        )
        self.assertFalse(Allocation.objects.exists())
        self.assertFalse(AccessGrant.objects.exists())
        self.assertEqual(access.current(self.org).plan.code, "manual-pilot")

    def test_observed_refund_dispute_and_failed_attempt_preserve_access_policy(self):
        operation = self.ready()
        event, _, _, _ = self.receipt(operation)
        services.process_event(self.owner, event.pk)
        original = MoneyEvent.objects.get(kind="payment")
        assignment = access.current(self.org)
        refund, _, _, _ = self.receipt(
            operation,
            kind="refund.observed",
            amount=200,
            reverses=original.effect_id,
            effect_id="refund-one",
        )
        services.process_event(self.owner, refund.pk)
        self.assertEqual(services.settled(self.statement), 800)
        self.assertEqual(services.statement_data(self.statement)["status"], "action_required")
        self.assertEqual(access.current(self.org).pk, assignment.pk)
        dispute, _, _, _ = self.receipt(operation, kind="dispute.observed")
        services.process_event(self.owner, dispute.pk)
        self.assertEqual(MoneyEvent.objects.count(), 2)
        self.assertEqual(access.current(self.org).pk, assignment.pk)

    def test_failed_and_cancelled_do_not_suspend_pilot(self):
        operation = self.ready()
        event, _, _, _ = self.receipt(operation, kind="payment.failed")
        services.process_event(self.owner, event.pk)
        self.assertEqual(access.current(self.org).plan.code, "manual-pilot")
        other = self.ready()
        event, _, _, _ = self.receipt(other, kind="subscription.cancelled")
        services.process_event(self.owner, event.pk)
        self.assertEqual(access.current(self.org).status, "active")
        self.assertFalse(MoneyEvent.objects.exists())

    def test_out_of_order_events_require_reconciliation(self):
        operation = self.ready()
        old, _, _, _ = self.receipt(operation)
        self.receipt(operation, kind="payment.failed")
        self.assertEqual(
            services.process_event(self.owner, old.pk).outcome, "ambiguous_object_version"
        )
        self.assertFalse(AccessGrant.objects.exists())

    def test_business_failure_rolls_back_money_and_access_but_retains_retryable_inbox(self):
        operation = self.ready()
        event, _, _, _ = self.receipt(operation)
        with patch("billing.services.access.assign", side_effect=RuntimeError("interrupted")):
            done = services.process_event(self.owner, event.pk)
        self.assertEqual(done.state, "retry")
        self.assertEqual(done.attempts, 1)
        self.assertFalse(MoneyEvent.objects.exists())
        self.assertFalse(Allocation.objects.exists())
        self.assertEqual(access.current(self.org).plan.code, "manual-pilot")
        self.assertEqual(services.process_event(self.owner, event.pk).state, "applied")
        self.assertEqual(MoneyEvent.objects.count(), 1)

    def test_tenant_roles_revocation_download_and_csrf_boundaries(self):
        detail = self.root + f"statements/{self.statement.pk}/"
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.get(detail + "download/").status_code, 200)
        self.assertIn("no-store", self.client.get(detail)["Cache-Control"])
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(detail).status_code, 404)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(detail + "download/").status_code, 403)
        membership = Membership.objects.get(organization=self.org, user=self.member)
        membership.role = "admin"
        membership.save()
        self.assertEqual(self.client.get(self.root).status_code, 200)
        membership.delete()
        self.assertEqual(self.client.get(self.root).status_code, 404)
        csrf = APIClient(enforce_csrf_checks=True)
        csrf.force_login(self.owner)
        self.assertEqual(
            csrf.post(
                self.root + "operations/",
                {"statement_id": str(self.statement.pk), "request_id": str(uuid.uuid4())},
                format="json",
            ).status_code,
            403,
        )

    @override_settings(BILLING_SIMULATOR_ENABLED=False)
    def test_disabled_collection_has_no_customer_action_and_no_trusted_ingress(self):
        self.assertFalse(services.account_summary(self.owner, self.org.pk)["collection_available"])
        with self.assertRaises(ValidationError):
            self.operation()
        response = APIClient().post(
            "/api/v1/billing/synthetic-inbox/", b"{}", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(AccessGrant.objects.exists())

    def test_no_simulator_rebind_of_live_account(self):
        org = create_organization(self.outsider, name="Unconfigured live", slug="unconfigured-live")
        account = BillingAccount.objects.get(organization=org)
        account.mode = "live"
        account.save()
        with self.assertRaises(services.Conflict):
            services.configure_simulator(self.outsider, org, reason="Denied crossover")

    def test_financial_database_guards_and_scope(self):
        operation = self.ready()
        event, _, _, _ = self.receipt(operation, amount=900)
        services.process_event(self.owner, event.pk)
        receipt = MoneyEvent.objects.get()
        with self.assertRaises(DatabaseError), transaction.atomic():
            Allocation.objects.create(statement=self.statement, money=receipt, amount_minor=901)
        for table in ("billing_moneyevent", "billing_allocation", "billing_billingaudit"):
            with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as c:
                c.execute(f"DELETE FROM {table}") if table != "billing_allocation" else c.execute(
                    "UPDATE billing_inbox SET payload='{}'::jsonb"
                )
        role = connection.ops.quote_name("ppi_billing_test_" + uuid.uuid4().hex[:10])
        with connection.cursor() as c:
            c.execute(f"CREATE ROLE {role} NOLOGIN NOINHERIT")
            c.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            c.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {role}")
            c.execute(f"SET LOCAL ROLE {role}")
        try:
            with self.assertRaises(DatabaseError), transaction.atomic():
                BillingAccount.objects.filter(pk=self.account.pk).update(customer_ref="forged")
            with self.assertRaises(DatabaseError), transaction.atomic():
                Statement.objects.filter(pk=self.statement.pk).update(state="draft")
            with self.assertRaises(DatabaseError), transaction.atomic():
                Allocation.objects.create(statement=self.statement, money=receipt, amount_minor=1)
        finally:
            with connection.cursor() as c:
                c.execute("RESET ROLE")

    def test_failed_receipt_storage_is_retryable_and_never_acknowledged(self):
        operation = self.ready()
        _, body, t, p = self.receipt(operation)
        with patch(
            "billing.services.Inbox.objects.create",
            side_effect=DatabaseError("synthetic storage failure"),
        ):
            changed = json.loads(body)
            changed["event_id"] = "storage-failure"
            raw = json.dumps(changed).encode()
            stamp, proof = adapter.sign(raw)
            response = self.client.post(
                "/api/v1/billing/synthetic-inbox/",
                raw,
                content_type="application/json",
                HTTP_X_PPI_TEST_TIME=stamp,
                HTTP_X_PPI_TEST_PROOF=proof,
            )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(Inbox.objects.filter(event_id="storage-failure").exists())
        self.assertFalse(MoneyEvent.objects.exists())

    def test_late_confirmation_is_credit_requiring_review(self):
        operation = self.ready()
        event, _, _, _ = self.receipt(operation)
        with patch(
            "billing.services.timezone.now",
            return_value=operation.expires_at + timedelta(seconds=1),
        ):
            done = services.process_event(self.owner, event.pk)
        self.assertEqual(done.outcome, "late_confirmation_unapplied_credit")
        self.assertFalse(AccessGrant.objects.exists())
        self.assertFalse(Allocation.objects.exists())
        self.assertEqual(MoneyEvent.objects.count(), 1)

    def test_account_wide_idempotency_rejects_another_statement(self):
        key = uuid.uuid4()
        services.request_operation(self.owner, self.org.pk, self.statement.pk, key)
        start = self.statement.period_end
        other = services.generate(
            self.owner,
            self.account,
            self.price,
            start=start,
            end=start + timedelta(days=30),
            reason="Another period",
        )
        other = services.finalize(self.owner, other, reason="Another period")
        with self.assertRaises(services.Conflict):
            services.request_operation(self.owner, self.org.pk, other.pk, key)
        self.assertEqual(PaymentOperation.objects.count(), 1)

    def test_expiry_dry_run_and_unknown_recovery_without_duplicate_request(self):
        operation = self.operation()
        before = GatewayCall.objects.count()
        services.reconcile_operation(self.owner, operation.pk, reason="Dry run")
        self.assertEqual(GatewayCall.objects.count(), before)
        with patch(
            "billing.services.timezone.now",
            return_value=operation.expires_at + timedelta(seconds=1),
        ):
            self.assertEqual(services.process_outbound(self.owner, operation.pk).state, "expired")
        self.assertFalse(GatewayObject.objects.exists())

    def test_abandoned_inbox_lease_is_fenced_before_recovery(self):
        operation = self.ready()
        event, _, _, _ = self.receipt(operation)
        _, old_lease = services.claim_event(self.owner, event.pk)
        Inbox.objects.filter(pk=event.pk).update(leased_at=timezone.now() - timedelta(seconds=91))
        recovered, new_lease = services.claim_event(self.owner, event.pk)
        obj = adapter.lookup(operation)
        self.assertNotEqual(old_lease, new_lease)
        services._apply_event(self.owner, event.pk, old_lease, obj)
        self.assertFalse(MoneyEvent.objects.exists())
        self.assertEqual(
            services._apply_event(self.owner, event.pk, new_lease, obj).state, "applied"
        )

    def test_reconciliation_recovers_missing_delivery_from_test_adapter_state(self):
        operation = self.ready()
        obj = GatewayObject.objects.get(operation=operation)
        obj.state = "paid"
        obj.version += 1
        obj.save()
        self.assertFalse(Inbox.objects.exists())
        services.reconcile_operation(
            self.owner, operation.pk, reason="Recover missing synthetic delivery", dry_run=False
        )
        event = Inbox.objects.get()
        self.assertEqual(event.state, "received")
        self.assertEqual(services.process_event(self.owner, event.pk).state, "applied")
        self.assertEqual(MoneyEvent.objects.count(), 1)

    def test_overpayment_and_excess_refund_never_overallocate(self):
        operation = self.ready()
        event, _, _, _ = self.receipt(operation, amount=1100)
        self.assertEqual(services.process_event(self.owner, event.pk).state, "quarantined")
        self.assertEqual(
            services.account_summary(self.owner, self.org.pk)["unapplied_credit"]["XTS"], "1100"
        )
        original = MoneyEvent.objects.get()
        refund, _, _, _ = self.receipt(
            operation,
            kind="refund.observed",
            amount=1101,
            reverses=original.effect_id,
            effect_id="excess-refund",
        )
        self.assertEqual(
            services.process_event(self.owner, refund.pk).outcome, "refund_amount_mismatch"
        )
        self.assertEqual(MoneyEvent.objects.count(), 1)
        self.assertFalse(Allocation.objects.exists())

    def test_valid_unsupported_event_is_ignored_and_public_amount_redirect_input_is_rejected(self):
        operation = self.ready()
        event, _, _, _ = self.receipt(operation, kind="unsupported.valid")
        self.assertEqual(services.process_event(self.owner, event.pk).state, "ignored")
        response = self.client.post(
            self.root + "operations/",
            {
                "statement_id": str(self.statement.pk),
                "request_id": str(uuid.uuid4()),
                "amount_minor": 1,
                "return_url": "https://untrusted.invalid",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.client.get(self.root + f"operations/{operation.pk}/").status_code, 200
        )
        self.client.force_authenticate(self.outsider)
        self.assertEqual(
            self.client.get(self.root + f"operations/{operation.pk}/").status_code, 404
        )

    def test_future_period_access_is_scheduled_and_manual_access_needs_explicit_replacement(self):
        future = self.statement.period_end
        draft = services.generate(
            self.owner,
            self.account,
            self.price,
            start=future,
            end=future + timedelta(days=30),
            access_transition=False,
            reason="No implicit access transition",
        )
        future_statement = services.finalize(self.owner, draft, reason="Future period")
        operation = services.request_operation(
            self.owner, self.org.pk, future_statement.pk, uuid.uuid4()
        )
        operation = services.process_outbound(self.owner, operation.pk)
        event, _, _, _ = self.receipt(operation)
        services.process_event(self.owner, event.pk)
        self.assertEqual(access.current(self.org).plan.code, "manual-pilot")
        self.assertFalse(AccessGrant.objects.exists())

    def test_verified_future_access_does_not_start_early(self):
        start = self.statement.period_end
        draft = services.generate(
            self.owner,
            self.account,
            self.price,
            start=start,
            end=start + timedelta(days=30),
            access_transition=True,
            reason="Explicit scheduled access",
        )
        item = services.finalize(self.owner, draft, reason="Future access")
        operation = services.request_operation(self.owner, self.org.pk, item.pk, uuid.uuid4())
        operation = services.process_outbound(self.owner, operation.pk)
        event, _, _, _ = self.receipt(operation)
        self.assertEqual(services.process_event(self.owner, event.pk).state, "applied")
        grant = AccessGrant.objects.get()
        self.assertEqual(grant.assignment.starts_at, start)
        self.assertEqual(access.current(self.org).plan.code, "manual-pilot")
        self.assertEqual(access.current(self.org, at=start).plan_id, self.plan.pk)


@override_settings(BILLING_SIMULATOR_ENABLED=True)
class ConcurrentBillingTests(Fixture, TransactionTestCase):
    def setUp(self):
        self.setup_billing()

    def race(self, fn):
        gate = Barrier(2)

        def worker(i):
            close_old_connections()
            try:
                gate.wait(timeout=15)
                return fn(i)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(worker, range(2)))

    def test_concurrent_request_same_identity_returns_one_operation(self):
        key = uuid.uuid4()
        result = self.race(
            lambda _: services.request_operation(self.owner, self.org.pk, self.statement.pk, key).pk
        )
        self.assertEqual(result[0], result[1])
        self.assertEqual(PaymentOperation.objects.count(), 1)

    def test_concurrent_equivalent_events_allocate_and_grant_once(self):
        operation = self.ready()
        first, body, _, _ = self.receipt(operation)
        data = json.loads(body)
        data["event_id"] = "second-equivalent"
        raw = json.dumps(data).encode()
        t, p = adapter.sign(raw)
        second = services.receive(raw, t, p)
        ids = [first.pk, second.pk]
        result = self.race(lambda i: services.process_event(self.owner, ids[i]).state)
        self.assertEqual(result, ["applied", "applied"])
        self.assertEqual(MoneyEvent.objects.count(), 1)
        self.assertEqual(Allocation.objects.count(), 1)
        self.assertEqual(AccessGrant.objects.count(), 1)

    def test_provider_boundary_runs_without_database_transaction(self):
        operation = self.operation()
        original = adapter.create

        def checked(item):
            self.assertFalse(connection.in_atomic_block)
            return original(item)

        with patch("billing.adapter.create", side_effect=checked):
            self.assertEqual(services.process_outbound(self.owner, operation.pk).state, "ready")
