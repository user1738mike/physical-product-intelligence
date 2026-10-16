"""Explicit operator identity + owner connection; never a customer mutation API."""

import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from commercial import services
from commercial.models import Plan
from organizations.models import Organization


class Command(BaseCommand):
    help = (
        "Publish immutable plans, assign/transition manual access, recover leases "
        "and reconcile usage. No payment requests."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=[
                "publish",
                "assign",
                "suspend",
                "resume",
                "expire",
                "recover",
                "reconcile",
                "adjust",
            ],
        )
        parser.add_argument("--actor", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--organization")
        parser.add_argument("--plan")
        parser.add_argument("--plan-version", type=int)
        parser.add_argument("--name")
        parser.add_argument("--policy-file", type=Path)
        parser.add_argument("--starts-at")
        parser.add_argument("--ends-at")
        parser.add_argument("--assignment")
        parser.add_argument("--usage")
        parser.add_argument("--operation")
        parser.add_argument("--amount", type=int)
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **o):
        try:
            actor = get_user_model().objects.get(username=o["actor"], is_active=True)
            services.operator(actor)
            if not o["reason"].strip():
                raise ValueError()

            def date(key):
                value = parse_datetime(o[key]) if o[key] else None
                if o[key] and (value is None or value.utcoffset() is None):
                    raise ValueError()
                return value

            if o["action"] == "publish":
                plan = services.publish(
                    actor,
                    code=o["plan"],
                    version=o["plan_version"],
                    name=o["name"],
                    policy=json.loads(o["policy_file"].read_text()),
                    reason=o["reason"],
                )
                result = {"plan_id": str(plan.pk)}
            else:
                org = Organization.objects.get(pk=o["organization"])
                if o["action"] == "assign":
                    plan = Plan.objects.get(code=o["plan"], version=o["plan_version"])
                    item = services.assign(
                        actor,
                        org,
                        plan,
                        reason=o["reason"],
                        starts_at=date("starts_at"),
                        ends_at=date("ends_at"),
                    )
                    result = {"assignment_id": str(item.pk)}
                elif o["action"] in {"suspend", "resume", "expire"}:
                    item = services.transition(
                        actor,
                        org,
                        o["assignment"],
                        action=o["action"],
                        reason=o["reason"],
                        ends_at=date("ends_at"),
                    )
                    result = {"assignment_id": str(item.pk), "status": item.status}
                elif o["action"] == "recover":
                    result = {
                        "recovered": services.recover(
                            actor, org, reason=o["reason"], limit=o["limit"]
                        )
                    }
                elif o["action"] == "adjust":
                    item = services.adjust(
                        actor,
                        org,
                        o["usage"],
                        amount=o["amount"],
                        operation=o["operation"],
                        reason=o["reason"],
                    )
                    result = {"adjustment_id": str(item.pk)}
                else:
                    result = services.reconcile(actor, org, reason=o["reason"])
            self.stdout.write(json.dumps(result, default=str))
        except Exception as error:
            # Arguments/configuration can contain operator text; never echo exception payloads.
            raise CommandError(
                "Commercial operation rejected; check identity, documented arguments, "
                "policy and database invariants."
            ) from error
