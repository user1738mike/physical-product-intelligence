"""Offline validation-boundary evaluation, not live-model accuracy measurement."""

import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from . import ai_schema, services


def evaluate():
    dataset = json.loads(
        Path(__file__).with_name("evals").joinpath("spec-v1.json").read_text(encoding="utf-8")
    )
    results = []
    for case in dataset["cases"]:
        items = ai_schema.decode(json.dumps(case["response"]))
        actual, operands = [], defaultdict(set)
        for item in items:
            schema = ai_schema.ExtractedValue(data=item)
            valid = schema.is_valid()
            grounded = valid and ai_schema.grounded(schema.validated_data, case["segments"])
            normalized = False
            if grounded:
                value = schema.validated_data
                try:
                    result = services.normalize(
                        value["attribute"], value["value"], value["unit"], timezone.now()
                    )
                    normalized = True
                    operands[value["attribute"]].add(
                        (Decimal(result["canonical_value"]), result["canonical_unit"])
                        if "canonical_value" in result
                        else result["value"]
                    )
                except ValidationError:
                    pass
            actual.append([bool(valid), bool(grounded), normalized])
        conflict = any(len(values) > 1 for values in operands.values())
        results.append(
            {
                "case": case["id"],
                "matched": actual == case["expected"] and conflict == case["conflict"],
                "candidate_count": len(items),
                "conflict_retained": conflict,
                "review_required": True,
            }
        )
    return {
        "evaluation_version": "validation-boundary-v1",
        "dataset_version": dataset["dataset_version"],
        "model": "recorded-mock-fixtures-v1",
        "provider_calls": 0,
        "cases": len(results),
        "case_expectations_matched": sum(row["matched"] for row in results),
        "results": results,
        "interpretation": (
            "Deterministic schema/grounding checks only; "
            "no live extraction accuracy, precision or recall claimed."
        ),
    }
