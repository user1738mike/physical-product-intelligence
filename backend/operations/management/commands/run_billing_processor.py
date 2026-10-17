import os
from pathlib import Path

from operations.billing_processor import cycle
from operations.management.commands.run_processors import Command as ProcessorCommand


class Command(ProcessorCommand):
    help = (
        "Supervised verified billing inbox and lookup-only reconciliation. Never creates payments."
    )
    default_interval = 30
    default_limit = 5
    maximum_limit = 10
    heartbeat = Path("/tmp/ppi-billing-processor-heartbeat")
    report_key = "billing_cycle"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--enabled",
            action="store_true",
            default=os.environ.get("PPI_BILLING_PROCESSOR_ENABLED") == "true",
        )

    def handle(self, *args, **options):
        if options["enabled"]:
            self.work = cycle
        else:
            from operations.processors import operator

            def disabled(actor, **kwargs):
                operator(actor)
                return {"lookups": 0, "events": 0, "unavailable": 1, "failures": 0}

            self.work = disabled
        return super().handle(*args, **options)
