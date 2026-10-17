from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from ingestion.retention import reconcile


class Command(BaseCommand):
    help = "Reconcile one uncertain removal after quiescing processors; never deletes files."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--removal", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--workers-quiesced", action="store_true")

    def handle(self, *args, **options):
        if not options["workers_quiesced"] or not 5 <= len(options["reason"]) <= 1000:
            raise CommandError("Quiesce workers and provide a non-sensitive case reason.")
        try:
            actor = get_user_model().objects.get(username=options["actor"])
            result = reconcile(actor, options["removal"], reason=options["reason"])
        except Exception:
            raise CommandError("Reconciliation failed; private diagnostics suppressed.") from None
        self.stdout.write(result.state)
