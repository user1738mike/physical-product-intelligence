import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from operations.models import RateBucket


class Command(BaseCommand):
    help = (
        "Dry-run by default. Remove expired operational counters only; "
        "never catalog/audit/source data."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        rows = RateBucket.objects.filter(expires_at__lt=timezone.now())
        count = rows.count()
        if options["apply"]:
            rows.delete()
        self.stdout.write(json.dumps({"expired_counters": count, "applied": options["apply"]}))
