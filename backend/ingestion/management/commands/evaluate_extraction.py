import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ingestion.evaluation import evaluate


class Command(BaseCommand):
    help = (
        "Evaluate versioned synthetic validation fixtures offline; no provider calls or DB writes."
    )
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--output")

    def handle(self, *args, **options):
        result = evaluate()
        if options["output"]:
            with Path(options["output"]).open("x", encoding="utf-8") as stream:
                json.dump(result, stream, indent=2)
        self.stdout.write(
            json.dumps({key: value for key, value in result.items() if key != "results"})
        )
        if result["cases"] != result["case_expectations_matched"]:
            raise CommandError("Synthetic validation expectation mismatch")
