import json

from django.core.management.base import BaseCommand, CommandError

from operations.recovery import backup


class Command(BaseCommand):
    help = "Create a protected database/private-file backup during an explicit maintenance window."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)
        parser.add_argument("--confirm-database", required=True)
        parser.add_argument("--pg-dump", default="pg_dump")
        parser.add_argument("--maintenance-window", action="store_true", required=True)

    def handle(self, *args, **options):
        try:
            result = backup(options["output"], options["confirm_database"], options["pg_dump"])
        except Exception:
            raise CommandError(
                "Backup failed safely; inspect target/configuration. No restore was attempted."
            ) from None
        self.stdout.write(json.dumps(result))
