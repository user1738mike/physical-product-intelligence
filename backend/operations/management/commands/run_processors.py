import json
import os
import signal
from pathlib import Path
from threading import Event

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from operations.processors import cycle


class Command(BaseCommand):
    help = "Supervised bounded webhook dispatch, abandoned-work recovery and counter cleanup."

    def add_arguments(self, parser):
        parser.add_argument("--actor", default=os.environ.get("PPI_PROCESSOR_ACTOR", ""))
        parser.add_argument("--interval", type=int, default=10)
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        if (
            not options["actor"]
            or not 1 <= options["interval"] <= 300
            or not 1 <= options["limit"] <= 100
        ):
            raise CommandError("Explicit operator, interval 1..300 and limit 1..100 required.")
        stop = Event()
        previous = {}
        if not options["once"]:
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous[sig] = signal.signal(sig, lambda *_: stop.set())
        try:
            while not stop.is_set():
                close_old_connections()
                try:
                    # Re-read identity every cycle: disabling an operator takes effect
                    # without restarting the service. No impersonation of tenant users.
                    actor = get_user_model().objects.get(username=options["actor"])
                    result = cycle(actor, limit=options["limit"])
                except Exception:
                    if options["once"]:
                        raise CommandError(
                            "Processor cycle failed; private diagnostics suppressed."
                        ) from None
                    result = {"failures": 1}
                self.stdout.write(json.dumps({"processor_cycle": result}))
                if not options["once"] and not result["failures"]:
                    Path("/tmp/ppi-processors-heartbeat").touch()
                if options["once"]:
                    break
                stop.wait(options["interval"])
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            close_old_connections()
