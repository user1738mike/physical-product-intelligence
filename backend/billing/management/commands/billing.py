"""Bounded operator workflow. Default processing/reconciliation mode is read-only dry run."""

import json
import uuid

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime

from billing import adapter, services
from billing.models import BillingAccount, GatewayObject, Inbox, PaymentOperation, Price, Statement
from commercial import services as access
from commercial.models import Plan
from organizations.models import Organization


class Command(BaseCommand):
    help = (
        "Publish internal prices/statements and process/reconcile bounded offline "
        "billing workflows."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=[
                "configure-simulator",
                "publish-price",
                "generate",
                "finalize",
                "revise",
                "adjust",
                "process",
                "reconcile",
                "simulate",
            ],
        )
        parser.add_argument("--actor", required=True)
        parser.add_argument("--reason", required=True)
        for key in (
            "organization",
            "plan",
            "price",
            "code",
            "currency",
            "mode",
            "start",
            "end",
            "statement",
            "operation",
            "kind",
            "reverses",
        ):
            parser.add_argument("--" + key)
        for key in (
            "plan-version",
            "price-version",
            "exponent",
            "unit-minor",
            "quantity",
            "expected-version",
            "amount-minor",
            "delta-minor",
        ):
            parser.add_argument("--" + key, type=int)
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--replace-access", action="store_true")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **o):
        try:
            actor = get_user_model().objects.get(username=o["actor"], is_active=True)
            access.operator(actor)
            if not o["reason"].strip() or not 1 <= o["limit"] <= 100:
                raise ValueError()
            action = o["action"]
            org = Organization.objects.get(pk=o["organization"]) if o["organization"] else None
            account = BillingAccount.objects.get(organization=org) if org else None
            if action == "configure-simulator":
                result = {
                    "account": str(services.configure_simulator(actor, org, reason=o["reason"]).pk)
                }
            elif action == "publish-price":
                plan = Plan.objects.get(code=o["plan"], version=o["plan_version"])
                price = services.publish_price(
                    actor,
                    code=o["code"],
                    version=o["price_version"],
                    plan=plan,
                    currency_code=o["currency"],
                    exponent=o["exponent"],
                    unit_minor=o["unit_minor"],
                    mode=o["mode"],
                    reason=o["reason"],
                )
                result = {"price": str(price.pk)}
            elif action == "generate":
                item = services.generate(
                    actor,
                    account,
                    Price.objects.get(pk=o["price"]),
                    start=parse_datetime(o["start"]),
                    end=parse_datetime(o["end"]),
                    quantity=o["quantity"] or 1,
                    access_transition=o["replace_access"],
                    reason=o["reason"],
                )
                result = {"statement": str(item.pk), "state": item.state}
            elif action in {"finalize", "revise", "adjust"}:
                item = Statement.objects.get(account=account, pk=o["statement"])
                if action == "finalize":
                    result = {
                        "statement": str(services.finalize(actor, item, reason=o["reason"]).pk)
                    }
                elif action == "revise":
                    result = {
                        "statement": str(
                            services.revise(
                                actor,
                                item,
                                quantity=o["quantity"],
                                expected_version=o["expected_version"],
                                reason=o["reason"],
                            ).pk
                        )
                    }
                else:
                    result = {
                        "adjustment": str(
                            services.adjust_statement(
                                actor,
                                item,
                                delta_minor=o["delta_minor"],
                                operation=uuid.UUID(o["operation"]),
                                reason=o["reason"],
                            ).pk
                        )
                    }
            elif action == "simulate":
                adapter.require()
                operation = PaymentOperation.objects.get(
                    statement__account=account, pk=o["operation"], mode="test", provider="simulator"
                )
                states = {
                    "payment.succeeded": "paid",
                    "payment.failed": "failed",
                    "subscription.cancelled": "cancelled",
                    "refund.observed": "refunded",
                    "dispute.observed": "disputed",
                }
                with transaction.atomic():
                    access.lock(org)
                    obj = GatewayObject.objects.select_for_update().get(operation=operation)
                    obj.version += 1
                    obj.state = states[o["kind"]]
                    if o["kind"] == "payment.succeeded" and o["amount_minor"] is not None:
                        obj.amount_minor = services.amount(o["amount_minor"], zero=False)
                    obj.save()
                    data = adapter.payload(
                        operation,
                        obj,
                        kind=o["kind"],
                        amount=o["amount_minor"],
                        reverses=o["reverses"] or "",
                        effect_id=("refund-" + obj.external_ref + "-" + str(obj.version))
                        if o["kind"] == "refund.observed"
                        else None,
                    )
                    body = json.dumps(data, sort_keys=True).encode()
                    timestamp, proof = adapter.sign(body)
                    event = services.receive(body, timestamp, proof)
                    services.audit(actor, account, "synthetic_event_created", event.pk, o["reason"])
                result = {"event": str(event.pk), "state": event.state, "real_payment": False}
            else:
                if account is None:
                    raise ValueError()
                operations = PaymentOperation.objects.filter(
                    statement__account=account,
                    state__in=["pending", "processing", "unknown", "ready"],
                ).order_by("created_at")[: o["limit"]]
                result = {"dry_run": not o["apply"], "operations": [], "events": []}
                for item in operations:
                    if not o["apply"] or action == "reconcile" or item.state != "pending":
                        result["operations"].append(
                            services.reconcile_operation(
                                actor, item.pk, reason=o["reason"], dry_run=not o["apply"]
                            )
                        )
                    else:
                        done = services.process_outbound(actor, item.pk)
                        result["operations"].append({"id": str(done.pk), "state": done.state})
                events = Inbox.objects.filter(
                    account=account, state__in=["received", "retry", "processing"]
                ).order_by("received_at")[: o["limit"]]
                for event in events:
                    done = services.process_event(actor, event.pk) if o["apply"] else event
                    result["events"].append({"id": str(done.pk), "state": done.state})
            self.stdout.write(json.dumps(result))
        except Exception as error:
            raise CommandError(
                "Billing operation rejected; inspect documented inputs, actor and tenant/mode "
                "policy. Private diagnostics suppressed."
            ) from error
