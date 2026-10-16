"""One controlled, database-identified migration owner; no startup replica races."""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Apply forward migrations under an exclusive PostgreSQL release lock."

    def add_arguments(self, parser):
        parser.add_argument("--confirm-database", required=True)

    def handle(self, *args, **options):
        if options["confirm_database"] != connection.settings_dict["NAME"]:
            raise CommandError("Release database identity mismatch")
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(hashtext(current_database()), 8)")
            if not cursor.fetchone()[0]:
                raise CommandError("Another release/migration owns the database lock")
        try:
            call_command("migrate", interactive=False, verbosity=0)
            call_command("migrate", check=True, verbosity=0)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(hashtext(current_database()), 8)")
        self.stdout.write("release_migrations_current")
