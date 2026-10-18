import json
import os
import signal
import time
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connection

from operations.processors import cycle


class Command(BaseCommand):
    help = "Supervised bounded webhook dispatch, abandoned-work recovery and counter cleanup."
    work = staticmethod(cycle)
    default_interval = 10
    default_limit = 20
    maximum_limit = 100
    heartbeat = Path("/tmp/ppi-processors-heartbeat")
    report_key = "processor_cycle"

    def add_arguments(self, parser):
        parser.add_argument("--actor", default=os.environ.get("PPI_PROCESSOR_ACTOR", ""))
        parser.add_argument("--interval", type=int, default=self.default_interval)
        parser.add_argument("--limit", type=int, default=self.default_limit)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        if (
            not options["actor"]
            or not 1 <= options["interval"] <= 300
            or not 1 <= options["limit"] <= self.maximum_limit
        ):
            raise CommandError("Explicit operator and documented bounded interval/limit required.")
        stopped = False

        def request_stop(*_):
            # Signal callbacks must not acquire Event/Condition locks: a signal
            # may interrupt wait() while the same thread holds that lock.
            nonlocal stopped
            stopped = True

        previous = {}
        if not options["once"]:
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous[sig] = signal.signal(sig, request_stop)
        try:
            while not stopped:
                close_old_connections()
                try:
                    if connection.vendor == "postgresql":
                        with connection.cursor() as cursor:
                            cursor.execute("SET statement_timeout=5000")
                            cursor.execute("SET lock_timeout=3000")
                            cursor.execute("SET idle_in_transaction_session_timeout=15000")
                    # Re-read identity every cycle: disabling an operator takes effect
                    # without restarting the service. No impersonation of tenant users.
                    actor = get_user_model().objects.get(username=options["actor"])
                    result = self.work(actor, limit=options["limit"])
                except Exception:
                    if options["once"]:
                        raise CommandError(
                            "Processor cycle failed; private diagnostics suppressed."
                        ) from None
                    result = {"failures": 1}
                self.stdout.write(json.dumps({self.report_key: result}))
                if not options["once"] and not result["failures"]:
                    self.heartbeat.touch()
                if options["once"]:
                    if result["failures"]:
                        raise CommandError(
                            "Processor cycle had failures; private diagnostics suppressed."
                        )
                    break
                until = time.monotonic() + options["interval"]
                while not stopped:
                    remaining = until - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(1, remaining))
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            close_old_connections()
