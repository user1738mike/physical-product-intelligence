import json

from django.core.management.base import BaseCommand, CommandError

from operations.recovery import restore


class Command(BaseCommand):
    help = (
        "Restore only into a confirmed empty isolated ppi_restore_ database and new private root."
    )

    def add_arguments(self, parser):
        parser.add_argument("--bundle", required=True)
        parser.add_argument("--confirm-target-database", required=True)
        parser.add_argument("--media-target", required=True)
        parser.add_argument("--pg-restore", default="pg_restore")

    def handle(self, *args, **options):
        try:
            result = restore(
                options["bundle"],
                options["confirm_target_database"],
                options["media_target"],
                options["pg_restore"],
            )
        except Exception:
            raise CommandError(
                "Restore refused/failed; target remains isolated. Never use a working database."
            ) from None
        self.stdout.write(json.dumps(result))
