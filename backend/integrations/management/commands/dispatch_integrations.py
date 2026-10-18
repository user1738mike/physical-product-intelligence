import json

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from commercial.services import operator
from integrations.models import Delivery
from integrations.services import dispatch_one
from organizations.models import Organization


class Command(BaseCommand):
    help = "Bounded organization-scoped outbound dispatcher; dry run by default."

    def add_arguments(self, parser):
        parser.add_argument("--organization", required=True)
        parser.add_argument("--actor", required=True)
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model
        from django.db import transaction

        try:
            actor = get_user_model().objects.get(username=options["actor"])
            operator(actor)
            org = Organization.objects.get(pk=options["organization"])
            if not 1 <= options["limit"] <= 100:
                raise ValueError()
            now = timezone.now()
            query = Delivery.objects.filter(event__organization=org, due_at__lte=now).filter(
                Q(state__in=["pending", "retryable"]) | Q(state="claimed", lease_until__lte=now)
            )
            ids = list(
                query.order_by("due_at", "pk").values_list("pk", flat=True)[: options["limit"]]
            )
            results = [dispatch_one(pk) for pk in ids] if options["apply"] else []
            if options["apply"]:
                from audit.services import record

                with transaction.atomic():
                    record(
                        "integration.dispatch_batch",
                        actor=actor,
                        organization=org,
                        target_type="organization",
                        target_id=org.pk,
                        metadata={"bounded_count": len(ids)},
                    )
            self.stdout.write(
                json.dumps(
                    {"dry_run": not options["apply"], "selected": len(ids), "results": results}
                )
            )
        except Exception:
            raise CommandError(
                "Bounded dispatch failed; inspect sanitized delivery history."
            ) from None
