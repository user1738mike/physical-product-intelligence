"""Separate opt-in synthetic integration check. Not imported/executed by startup or CI."""

import json
import time
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand

from ingestion import ai_provider, ai_schema, services


class Command(BaseCommand):
    help = "Explicitly authorized live integration only; one synthetic request, no database writes."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--allow-live-provider", action="store_true")

    def handle(self, *args, **options):
        if not options["allow_live_provider"]:
            self.stdout.write(
                json.dumps(
                    {"status": "not_executed", "reason": "explicit_live_authorization_required"}
                )
            )
            return
        segments = [
            {
                "id": 1,
                "location": "synthetic integration fixture",
                "text": "Synthetic carton specification. Weight: 1200 g. Length: 10 cm.",
            }
        ]
        started = time.monotonic()
        status, category, known = "failed", "validation", 0
        try:
            provider = ai_provider.configured_provider(max_output_tokens=400)
            raw, usage = provider.extract(segments)
            items = ai_schema.decode(raw)
            mass = False
            for item in items:
                parsed = ai_schema.ExtractedValue(data=item)
                parsed.is_valid(raise_exception=True)
                value = parsed.validated_data
                if not ai_schema.grounded(value, segments):
                    raise ValueError("Ungrounded candidate")
                normalized = services.normalize(
                    value["attribute"], value["value"], value["unit"], "2026-01-01T00:00:00Z"
                )
                known += 1
                mass = (
                    mass
                    or value["attribute"] == "mass"
                    and Decimal(normalized["canonical_value"]) == Decimal("1.2")
                )
            if mass:
                status, category = "passed", "schema_and_synthetic_mass_valid"
        except ai_provider.ProviderFailure as error:
            category = error.category
        except Exception:
            category = "invalid_response"
        self.stdout.write(
            json.dumps(
                {
                    "status": status,
                    "category": category,
                    "model": settings.AI_EXTRACTION_MODEL,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "valid_candidates": known,
                    "quality_claim": "none_single_synthetic_check",
                }
            )
        )
