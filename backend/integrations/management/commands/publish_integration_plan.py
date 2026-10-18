"""Explicit owner-only new plan publication; never edits an existing definition or price."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from commercial import services
from commercial.models import FEATURES, METERS, Plan
from integrations.models import PlanPolicy


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--base-plan", required=True)
        parser.add_argument("--plan-version", required=True, type=int)
        parser.add_argument("--credentials-limit", type=int, default=3)
        parser.add_argument("--destinations-limit", type=int, default=2)
        parser.add_argument("--reason", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            actor = get_user_model().objects.get(username=options["actor"])
            services.operator(actor)
            base = Plan.objects.get(pk=options["base_plan"])
            if (
                options["plan_version"] <= base.version
                or not options["reason"].strip()
                or not 0 <= options["credentials_limit"] <= 20
                or not 0 <= options["destinations_limit"] <= 10
            ):
                raise ValueError()
            plan = services.publish(
                actor,
                code=base.code,
                version=options["plan_version"],
                name=base.name,
                policy={
                    key: getattr(base, key)
                    for key in (*FEATURES, *(meter + "_limit" for meter in METERS))
                },
                reason=options["reason"],
            )
            PlanPolicy.objects.create(
                plan=plan,
                api_enabled=True,
                webhooks_enabled=True,
                credentials_limit=options["credentials_limit"],
                destinations_limit=options["destinations_limit"],
            )
            self.stdout.write(str(plan.pk))
        except Exception:
            raise CommandError(
                "Integration plan publication failed; verify reviewed version and limits."
            ) from None
