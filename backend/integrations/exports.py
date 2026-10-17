"""Versioned projection of frozen snapshots; no file URLs or mutable current measurements."""

import csv
import io
import json

from rest_framework.exceptions import ValidationError

MAX_BYTES = 1024 * 1024


def project(item):
    # Evidence metadata in the frozen input is reduced to opaque references, never source URLs.
    def safe(value):
        if isinstance(value, dict):
            return {
                key: safe(child)
                for key, child in value.items()
                if key
                not in {
                    "url",
                    "source_url",
                    "source_reference",
                    "file",
                    "file_url",
                    "download_path",
                    "storage_key",
                    "object_key",
                    "created_by_id",
                    "modified_by_id",
                    "verified_by_id",
                    "creator_id",
                }
            }
        if isinstance(value, list):
            return [safe(child) for child in value]
        return value

    return {
        "schema_version": "1",
        "assessment_id": str(item.pk),
        "organization_id": str(item.organization_id),
        "assessed_at": item.created_at.isoformat(),
        "overall": item.overall,
        "engine_version": item.engine_version,
        "product_id": str(item.product_id),
        "product_revision_id": str(item.product_revision_id),
        "packaging_revision_id": str(item.packaging_revision_id)
        if item.packaging_revision_id
        else None,
        "equipment_revision_id": str(item.equipment_revision_id),
        "rule_set_id": str(item.rule_set_id),
        "inputs": safe(item.inputs),
        "equipment_snapshot": safe(item.equipment_snapshot),
        "rule_snapshot": safe(item.rule_snapshot),
        "results": safe(item.results),
        "summary": item.summary,
        "notice": "An assessment export is not a safety certificate or measured-performance proof.",
    }


def bounded_json(value):
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    if len(body) > MAX_BYTES:
        raise ValidationError(
            {
                "code": "export_limit",
                "detail": "Response exceeds the 1 MiB limit; narrow the request.",
            }
        )
    return body


def csv_text(value):
    # Prefix potentially active spreadsheet text. JSON retains the exact original value.
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    )
    return (
        "'" + text
        if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@"))
        or text.startswith(("\t", "\r", "\n"))
        else text
    )


def export(item, format):
    data = project(item)
    if format == "json":
        return bounded_json(data), "application/json"
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    columns = [
        "schema_version",
        "assessment_id",
        "assessed_at",
        "overall",
        "engine_version",
        "product_revision_id",
        "packaging_revision_id",
        "equipment_revision_id",
        "rule_set_id",
        "summary",
        "inputs_json",
        "equipment_snapshot_json",
        "rule_snapshot_json",
        "results_json",
    ]
    writer.writerow(columns)
    writer.writerow([csv_text(data[key.removesuffix("_json")]) for key in columns])
    body = output.getvalue().encode("utf-8")
    if len(body) > MAX_BYTES:
        raise ValidationError({"code": "export_limit", "detail": "CSV exceeds the 1 MiB limit."})
    return body, "text/csv; charset=utf-8"
