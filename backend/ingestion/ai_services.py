"""Bounded, explicit processing leases over existing import/review records."""

import hashlib
import json
import time
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from products import services as catalog
from products import workflows

from . import ai_provider, ai_schema, parsers, services
from .models import Candidate, ImportJob, ImportRow, ReviewRecord
from .storage import read_upload


def require_ai(job):
    if job.mode != "ai":
        raise ValidationError("Select an AI extraction job.")


def source_valid(job):
    source = job.source_job
    if (
        not source
        or source.organization_id != job.organization_id
        or source.mode != "deterministic"
        or source.sha256 != job.sha256
        or source.storage_key != job.storage_key
    ):
        raise ValidationError("Extraction source scope or identity is invalid.")
    read_upload(source)


@transaction.atomic
def start(actor, org_id, source_id, values):
    source = services.job_in(actor, org_id, source_id, lock=True, reviewer=True)
    if source.mode != "deterministic":
        raise ValidationError("Extract from an original uploaded document, not another extraction.")
    fingerprint = hashlib.sha256(
        json.dumps({**values, "source": str(source.pk)}, sort_keys=True, default=str).encode()
    ).hexdigest()
    old = ImportJob.objects.filter(
        organization=source.organization, request_id=values["request_id"]
    ).first()
    if old:
        if old.extraction["request_sha256"] != fingerprint:
            raise catalog.Conflict("Request identifier already names different extraction targets.")
        return old
    ready, category = ai_provider.availability()
    if not ready:
        raise Unavailable(category)
    product = catalog.product_in(source.organization, values["product_id"])
    catalog.require_active(product)
    package = (
        workflows.configuration_in(product, values["packaging_id"])
        if values["packaging_id"]
        else None
    )
    if package and not package.is_active:
        raise ValidationError("Select active packaging.")
    read_upload(source)
    if (
        ImportJob.objects.filter(organization=source.organization)
        .exclude(status__in=services.TERMINAL)
        .count()
        >= 20
    ):
        raise ValidationError("At most 20 unfinished imports are permitted per organization.")
    job = ImportJob.objects.create(
        organization=source.organization,
        created_by=actor,
        source_job=source,
        mode="ai",
        request_id=values["request_id"],
        storage_key=source.storage_key,
        display_name=source.display_name,
        format=source.format,
        size=source.size,
        sha256=source.sha256,
        scan_status=source.scan_status,
        parser_version=ai_schema.VERSION,
        mapping={"sku": "sku"},
        options=source.options,
        extraction={
            "request_sha256": fingerprint,
            "product_id": str(product.pk),
            "packaging_id": str(package.pk) if package else None,
            "provider": "openai",
            "model": settings_model(),
            "schema_version": ai_schema.VERSION,
            "attempts": 0,
            "retryable": False,
            "stage": "queued",
        },
    )
    services.event(job, actor, "extraction_queued")
    return job


def settings_model():
    from django.conf import settings

    return settings.AI_EXTRACTION_MODEL


class Unavailable(ValidationError):
    status_code = 503

    def __init__(self, category):
        super().__init__(
            {
                "detail": "AI extraction unavailable; deterministic import and manual review "
                "remain available.",
                "code": category,
            }
        )


@transaction.atomic
def claim(actor, org, job_id, values):
    job = services.job_in(actor, org, job_id, lock=True, reviewer=True)
    require_ai(job)
    if connection.vendor == "postgresql":
        # Serialize admission across tenants/instances; no lock is held during provider work.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(73412891)")
    if job.status in {"awaiting_review", "completed", "completed_with_errors", "cancelled"}:
        return job, None
    if (
        job.status == "processing"
        and job.started_at
        and job.started_at > timezone.now() - timedelta(seconds=90)
    ):
        return job, None
    services.version(job, values["expected_version"])
    if job.status == "failed" and not job.extraction.get("retryable"):
        raise catalog.Conflict(
            "This permanent failure requires a corrected source and a new extraction."
        )
    if job.extraction["attempts"] >= 3:
        raise catalog.Conflict("Extraction attempt limit reached.")
    ready, category = ai_provider.availability()
    if not ready:
        raise Unavailable(category)
    source_valid(job)
    if (
        ImportJob.objects.filter(
            mode="ai", status="processing", started_at__gt=timezone.now() - timedelta(seconds=90)
        )
        .exclude(pk=job.pk)
        .count()
        >= settings.AI_EXTRACTION_MAX_CONCURRENT
    ):
        raise catalog.Conflict("Extraction processing capacity reached; wait or cancel stale work.")
    if (
        ImportJob.objects.filter(
            organization=job.organization,
            mode="ai",
            status="processing",
            started_at__gt=timezone.now() - timedelta(seconds=90),
        )
        .exclude(pk=job.pk)
        .exists()
    ):
        raise catalog.Conflict("Another extraction is processing; wait or cancel it first.")
    lease = str(uuid.uuid4())
    job.status, job.started_at, job.errors = "processing", timezone.now(), []
    job.extraction.update(
        lease=lease,
        stage="processing",
        attempts=job.extraction["attempts"] + 1,
        model=settings_model(),
        retryable=False,
    )
    services.save_job(job)
    ReviewRecord.objects.create(
        job=job,
        actor=actor,
        action="extraction_started",
        reason="Explicit provider processing request",
        after={
            "attempt": job.extraction["attempts"],
            "model": settings_model(),
            "schema": ai_schema.VERSION,
        },
    )
    services.event(job, actor, "extraction_started")
    return job, lease


def process(actor, org, job_id, values):
    job, lease = claim(actor, org, job_id, values)
    if lease is None:
        return job
    started = time.monotonic()
    try:
        segments = parsers.parse(job.source_job, {**job.options, "_ai_segments": True})["segments"]
        if (
            not segments
            or len(segments) > 80
            or sum(len(s["text"]) for s in segments) > ai_schema.MAX_TEXT
        ):
            raise ai_provider.ProviderFailure("source_limit")
        raw, usage = ai_provider.configured_provider().extract(segments)
        items = ai_schema.decode(raw)
        return finish(actor, org, job_id, lease, segments, items, usage, time.monotonic() - started)
    except ai_provider.ProviderFailure as error:
        return failed(
            actor, org, job_id, lease, error.category, error.retryable, time.monotonic() - started
        )
    except (ValueError, TypeError, KeyError):
        return failed(
            actor, org, job_id, lease, "invalid_output", False, time.monotonic() - started
        )
    except ValidationError:
        return failed(
            actor, org, job_id, lease, "source_or_target_invalid", False, time.monotonic() - started
        )
    except Exception:
        # Never persist/log provider exception bodies, requests, source text or credentials.
        return failed(
            actor, org, job_id, lease, "processing_failed", False, time.monotonic() - started
        )


@transaction.atomic
def failed(actor, org, job_id, lease, category, retryable, duration):
    job = services.job_in(actor, org, job_id, lock=True, reviewer=True)
    if job.status != "processing" or job.extraction.get("lease") != lease:
        return job
    job.status, job.completed_at = "failed", timezone.now()
    job.errors = [
        {
            "code": category,
            "message": "Extraction failed safely ("
            + category
            + "). Source and catalog values were preserved.",
        }
    ]
    job.extraction.update(
        stage="failed",
        retryable=retryable and job.extraction["attempts"] < 3,
        duration_ms=round(duration * 1000),
    )
    services.save_job(job)
    ReviewRecord.objects.create(
        job=job,
        actor=actor,
        action="extraction_failed",
        reason="Bounded extraction failed",
        after={"category": category, "retryable": job.extraction["retryable"]},
    )
    services.event(job, actor, "extraction_failed")
    return job


@transaction.atomic
def finish(actor, org, job_id, lease, segments, items, usage, duration):
    job = services.job_in(actor, org, job_id, lock=True, reviewer=True)
    if job.status != "processing" or job.extraction.get("lease") != lease:
        return job
    source_valid(job)
    product = catalog.product_in(job.organization, job.extraction["product_id"])
    catalog.require_active(product)
    package = (
        workflows.configuration_in(product, job.extraction["packaging_id"])
        if job.extraction["packaging_id"]
        else None
    )
    if package and not package.is_active:
        raise ValidationError("Packaging is archived.")
    invalid = 0
    seen = {}
    for index, item in enumerate(items, 1):
        checked = ai_schema.ExtractedValue(data=item)
        valid = checked.is_valid()
        value = (
            checked.validated_data
            if valid
            else {
                "attribute": "unresolved",
                "original": item.get("original", "")[:2000]
                if isinstance(item, dict) and isinstance(item.get("original"), str)
                else "",
                "value": item.get("value", "")[:2000]
                if isinstance(item, dict) and isinstance(item.get("value"), str)
                else None,
                "unit": "",
                "quote": "",
                "segment": None,
            }
        )
        supported = ai_schema.grounded(value, segments) if valid else False
        segment = ai_schema.source_segment(value, segments) if valid else None
        issues = (
            []
            if supported
            else [
                "Unknown, malformed or unsupported candidate; source grounding "
                "unavailable. Reject and use manual source review."
            ]
        )
        normalized, existing, quality = {}, [], "invalid"
        row = ImportRow.objects.create(
            job=job,
            number=index,
            location=segment["location"] if segment else "Source location unavailable",
            raw={"sku": product.sku},
            sku=product.sku,
            product=product,
            packaging=package,
            expected_revision=product.revisions.first().number,
            expected_packaging_version=package.version if package else None,
        )
        if supported:
            try:
                normalized = services.normalize(
                    value["attribute"], value["value"], value["unit"], job.created_at
                )
                existing, quality = services.comparison(row, value["attribute"], normalized)
                operand = (
                    (Decimal(normalized["canonical_value"]), normalized["canonical_unit"])
                    if "canonical_value" in normalized
                    else normalized["value"]
                )
                signature = (value["attribute"], operand)
                if signature in seen:
                    quality = "duplicate" if normalized == seen[signature] else "equivalent"
                seen[signature] = normalized
            except ValidationError:
                issues = [
                    "Candidate value/type/unit failed deterministic validation; "
                    "correct explicitly before approval."
                ]
        invalid += bool(issues)
        Candidate.objects.create(
            row=row,
            field=value["attribute"],
            raw_value=value["original"],
            proposed={"value": value["value"] or "", "unit": value["unit"]},
            normalized=normalized,
            existing=existing,
            quality=quality,
            errors=issues,
            extraction={
                "method": "ai_extracted",
                "provider": job.extraction["provider"],
                "model": job.extraction["model"],
                "schema_version": ai_schema.VERSION,
                "extracted_at": timezone.now().isoformat(),
                "source_job_id": str(job.source_job_id),
                "source_sha256": job.sha256,
                "segment": value["segment"] if segment else None,
                "quote": value["quote"],
                "grounded": supported,
                "validation": "unknown"
                if valid and value["value"] is None
                else "valid"
                if not issues
                else "invalid",
                "data_type": "decimal" if value["attribute"] in services.NUMERIC else "text",
                "confidence": None,
            },
        )
    services.annotate_competitors(job)
    job.status = "awaiting_review" if items else "completed_with_errors"
    job.completed_at = timezone.now()
    job.counters = {
        "candidates": len(items),
        "invalid_candidates": invalid,
        "approved": 0,
        "rejected": 0,
        "awaiting_review": len(items),
    }
    job.extraction.update(
        stage=job.status,
        retryable=False,
        duration_ms=round(duration * 1000),
        usage={
            key: int(val)
            for key, val in usage.items()
            if key in {"input_tokens", "output_tokens", "total_tokens"}
            and isinstance(val, int)
            and 0 <= val <= 1000000
        },
        source_text_sha256=hashlib.sha256(
            json.dumps(segments, sort_keys=True).encode()
        ).hexdigest(),
        segments=len(segments),
    )
    if not items:
        job.errors = [
            {
                "code": "no_candidates",
                "message": "No supported facts extracted. Use deterministic import or manual "
                "evidence review.",
            }
        ]
    services.save_job(job)
    ReviewRecord.objects.create(
        job=job,
        actor=actor,
        action="extraction_finished",
        reason="Candidates persisted for explicit review; catalog unchanged",
        after={"candidates": len(items), "invalid": invalid},
    )
    services.event(job, actor, "extraction_finished")
    return job
