from collections import Counter, defaultdict
from decimal import Decimal

from django.conf import settings
from django.core.files.storage import storages
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from audit.services import record
from organizations.services import ADMIN, OWNER, authorize
from products import services as catalog
from products import workflows
from products.models import Evidence, Product
from products.workflow_serializers import ClaimInput, ConfigurationInput, ProductEditInput

from . import parsers
from .models import Candidate, ImportJob, ImportRow, ReviewRecord
from .serializers import NUMERIC, PRODUCT_FIELDS
from .storage import store_upload

REVIEWERS = {OWNER, ADMIN}
TERMINAL = {"completed", "completed_with_errors", "cancelled"}


def event(job, actor, action):
    record(
        f"import.{action}",
        actor=actor,
        organization=job.organization,
        target_type="importjob",
        target_id=job.pk,
    )


def job_in(actor, organization_id, job_id, *, lock=False, reviewer=False):
    org, _ = authorize(actor, organization_id, roles=REVIEWERS if reviewer else None, lock=lock)
    query = ImportJob.objects.filter(organization=org)
    if lock:
        query = query.select_for_update()
    try:
        return query.get(pk=job_id)
    except ImportJob.DoesNotExist as error:
        raise NotFound("Import job not found.") from error


def version(item, expected):
    if item.version != expected:
        raise catalog.Conflict("This import changed. Reload before continuing.")


def require_state(job, states):
    if job.status not in states:
        raise catalog.Conflict("This action is not allowed in the current import state.")


def deterministic(job):
    if job.mode != "deterministic":
        raise ValidationError("Use the AI extraction processing action for this job.")


def save_job(job):
    job.version += 1
    job.save()


def upload(actor, organization_id, file):
    saved = None
    try:
        with transaction.atomic():
            org, _ = authorize(actor, organization_id, lock=True)
            if (
                ImportJob.objects.filter(organization=org).exclude(status__in=TERMINAL).count()
                >= 20
            ):
                raise ValidationError(
                    "At most 20 unfinished imports are permitted per organization."
                )
            used = (
                ImportJob.objects.filter(organization=org, mode="deterministic").aggregate(
                    total=Sum("size")
                )["total"]
                or 0
            )
            if used + file.size > settings.INGESTION_LIMITS["storage_bytes"]:
                raise ValidationError("Organization upload storage limit reached.")
            saved = store_upload(file, org)
            job = ImportJob.objects.create(organization=org, created_by=actor, **saved)
            event(job, actor, "uploaded")
            return job
    except Exception:
        if saved:
            storages["ingestion"].delete(saved["storage_key"])
        raise


@transaction.atomic
def validate(actor, org, job_id, values):
    job = job_in(actor, org, job_id, lock=True)
    deterministic(job)
    version(job, values.pop("expected_version"))
    require_state(job, {"uploaded", "failed"})
    job.status = "validating"
    job.started_at = timezone.now()
    try:
        parsed = parsers.parse(job, values)
    except ValidationError as error:
        job.status = "failed"
        job.preview, job.mapping = {}, {}
        job.errors = [{"code": "parse_failed", "message": str(error.detail[0])}]
        save_job(job)
        event(job, actor, "validation_failed")
        return job
    headers = parsed["headers"]
    job.options = values
    job.mapping = {}
    # Suggestions use exact canonical names/one explicit alias, never fuzzy matches.
    aliases = {"weight": "mass", "units per package": "quantity", "product name": "name"}
    from .serializers import FIELDS

    suggestions = {}
    for header in headers:
        canonical = aliases.get(header.lower(), header.lower().replace(" ", "_"))
        if canonical in FIELDS:
            if canonical in suggestions:
                suggestions[canonical] = ""
            else:
                suggestions[canonical] = header
    job.preview = {
        "headers": headers,
        "sheets": parsed.get("sheets", []),
        "suggestions": {k: v for k, v in suggestions.items() if v},
        "sample": parsed["rows"][:5],
        "row_count": len(parsed["rows"]),
    }
    job.status, job.errors = "uploaded", []
    save_job(job)
    event(job, actor, "validated")
    return job


@transaction.atomic
def map_fields(actor, org, job_id, values):
    job = job_in(actor, org, job_id, lock=True)
    deterministic(job)
    version(job, values["expected_version"])
    require_state(job, {"uploaded"})
    headers = job.preview.get("headers", [])
    if not headers or set(values["mapping"].values()) - set(headers):
        raise ValidationError("Validate the file and map existing headers only.")
    previous = job.mapping
    job.mapping = values["mapping"]
    save_job(job)
    ReviewRecord.objects.create(
        job=job,
        actor=actor,
        action="mapping",
        reason="Explicit source mapping",
        before=previous,
        after=job.mapping,
    )
    event(job, actor, "mapping_changed")
    return job


def normalize(field, value, unit, observed):
    if value.startswith(("=", "+", "@")) or value == "[UNSUPPORTED FORMULA]":
        raise ValidationError("Formula-like cells are unsupported; supply literal values.")
    if field in NUMERIC:
        checked = catalog.validated(
            ClaimInput,
            {
                "attribute": field,
                "basis": "reported",
                "value": value,
                "unit": unit,
                "observed_at": observed,
                "evidence_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        canonical = workflows.canonical_fields(checked)
        return {
            "value": str(checked["value"]),
            "unit": unit,
            "canonical_value": str(canonical["canonical_value"]),
            "canonical_unit": canonical["canonical_unit"],
        }
    if field in PRODUCT_FIELDS:
        checked = catalog.validated(
            ProductEditInput,
            {field: value, "expected_revision": 1, "change_reason": "Import validation"},
        )
        return {"value": checked[field]}
    if field == "package_name":
        if not value or len(value) > 160:
            raise ValidationError("Package name must contain 1–160 characters.")
        return {"value": value}
    if field == "package_type":
        if value not in {"unit", "inner", "case", "pallet"}:
            raise ValidationError("Package type must be unit, inner, case or pallet.")
        return {"value": value}
    if field == "quantity":
        if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 1000000:
            raise ValidationError("Units per package must be an integer from 1 to 1000000.")
        return {"value": int(value)}
    if field == "material":
        if len(value) > 200:
            raise ValidationError("Material is limited to 200 characters.")
        return {"value": value}
    raise ValidationError("Unsupported target field.")


def comparison(row, field, normalized):
    existing = []
    if row.product_id:
        if field in NUMERIC:
            intended_package = row.raw.get(row.job.mapping.get("package_name"), "").strip()
            if intended_package and not row.packaging_id:
                return [], "new"
            for claim in workflows.claims_in(row.product, row.packaging).filter(attribute=field):
                existing.append(
                    {
                        "id": str(claim.pk),
                        "value": str(claim.canonical_value),
                        "unit": claim.canonical_unit,
                        "lower": str(claim.canonical_lower),
                        "upper": str(claim.canonical_upper),
                        "basis": claim.basis,
                    }
                )
            if existing:
                state = next(
                    s
                    for s in workflows.attribute_states(row.product, row.packaging)["results"]
                    if s["attribute"] == field
                )
                selected_id = str(state["selected_claim"].pk) if state["selected_claim"] else None
                for item in existing:
                    item["selected"] = item["id"] == selected_id
                equivalent = all(
                    Decimal(c["value"]) == Decimal(normalized["canonical_value"])
                    and c["lower"] == "None"
                    and c["upper"] == "None"
                    for c in existing
                )
                return existing, "equivalent" if equivalent else "conflict"
        elif field in PRODUCT_FIELDS:
            value = getattr(row.product.revisions.first(), field)
            if value:
                existing = [{"value": value}]
        elif row.packaging_id:
            attr = {"package_name": "name", "package_type": "level"}.get(field, field)
            value = getattr(row.packaging, attr)
            if value is not None and value != "":
                existing = [{"value": value}]
    return existing, (
        "equivalent" if existing[0]["value"] == normalized["value"] else "conflict"
    ) if existing else "new"


def error_messages(error):
    # Domain errors are fixed validation messages, not parser exceptions/paths.
    return [str(error.detail)[:500]]


@transaction.atomic
def process(actor, org, job_id, values):
    job = job_in(actor, org, job_id, lock=True)
    deterministic(job)
    if job.status == "awaiting_review":
        return job
    version(job, values["expected_version"])
    require_state(job, {"uploaded"})
    if not job.mapping or not job.preview:
        raise ValidationError("Validate and explicitly confirm a mapping first.")
    parsed = parsers.parse(job, job.options)
    job.status = "processing"
    seen = set()
    seen_rows = set()
    for source in parsed["rows"]:
        raw = source["cells"]
        mapped = {field: raw.get(column, "").strip() for field, column in job.mapping.items()}
        sku = mapped.get("sku", "")
        errors = list(source["errors"])
        row_signature = tuple(sorted(mapped.items()))
        if row_signature in seen_rows:
            errors.append("Duplicate mapped row retained for review; reject its candidates.")
        seen_rows.add(row_signature)
        try:
            catalog.validated(
                catalog.ProductCreateInput,
                {
                    "sku": sku,
                    "revision": {"name": "Validation", "change_reason": "Import validation"},
                },
            )
        except ValidationError:
            errors.append("SKU is missing or invalid; correct the source and upload again.")
            sku = ""
        product = (
            Product.objects.filter(organization=job.organization, sku=sku).first() if sku else None
        )
        package = None
        if product and mapped.get("package_name"):
            package = product.configurations.filter(name=mapped["package_name"]).first()
        row = ImportRow.objects.create(
            job=job,
            number=source["number"],
            location=source["location"],
            raw=raw,
            sku=sku,
            product=product,
            expected_revision=product.revisions.first().number if product else None,
            packaging=package,
            expected_packaging_version=package.version if package else None,
            errors=errors,
        )
        for field, value in mapped.items():
            if field in {"sku", "dimension_unit", "mass_unit"} or not value:
                continue
            unit = (
                mapped.get("mass_unit" if field == "mass" else "dimension_unit", "")
                if field in NUMERIC
                else ""
            )
            normalized, issues, quality, existing = {}, [], "invalid", []
            try:
                normalized = normalize(field, value, unit, job.created_at)
                existing, quality = comparison(row, field, normalized)
                signature = (sku, mapped.get("package_name", ""), field, str(normalized))
                if signature in seen:
                    quality = "duplicate"
                seen.add(signature)
            except ValidationError as error:
                issues = error_messages(error)
            Candidate.objects.create(
                row=row,
                field=field,
                raw_value=value,
                proposed={"value": value, "unit": unit},
                normalized=normalized,
                quality=quality,
                existing=existing,
                errors=issues,
            )
    job.status = "awaiting_review"
    annotate_competitors(job)
    job.counters = {
        "rows": job.rows.count(),
        "candidates": Candidate.objects.filter(row__job=job).count(),
        "invalid_rows": sum(bool(r.errors) for r in job.rows.all()),
        "conflicts": Candidate.objects.filter(row__job=job, quality="conflict").count(),
        "invalid_candidates": Candidate.objects.filter(row__job=job, quality="invalid").count(),
    }
    save_job(job)
    event(job, actor, "processed")
    return job


def annotate_competitors(job):
    candidates = list(Candidate.objects.filter(row__job=job).select_related("row"))
    groups = defaultdict(list)
    for candidate in candidates:
        package_name = candidate.row.raw.get(job.mapping.get("package_name"), "").strip()
        groups[(candidate.row.sku, package_name, candidate.field)].append(candidate)

    def signature(candidate):
        n = candidate.normalized
        return (
            (Decimal(n["canonical_value"]), n["canonical_unit"])
            if "canonical_value" in n
            else n.get("value")
        )

    for candidate in candidates:
        package_column = job.mapping.get("package_name")
        package_name = candidate.row.raw.get(package_column, "").strip()
        peers = [
            c
            for c in groups[(candidate.row.sku, package_name, candidate.field)]
            if c.pk != candidate.pk
            and c.row.sku == candidate.row.sku
            and c.row.raw.get(package_column, "").strip() == package_name
            and c.field == candidate.field
            and c.normalized
            and signature(c) != signature(candidate)
        ]
        candidate.proposed["competing"] = [
            dict(candidate_id=str(c.pk), **c.normalized) for c in peers
        ][:10]
        if peers and candidate.normalized:
            candidate.quality = "conflict"
        candidate.save()


def candidate_in(job, candidate_id):
    try:
        return Candidate.objects.select_related("row__product", "row__packaging").get(
            row__job=job, pk=candidate_id
        )
    except Candidate.DoesNotExist as error:
        raise NotFound("Candidate not found.") from error


@transaction.atomic
def review(actor, org, job_id, candidate_id, values):
    job = job_in(actor, org, job_id, lock=True, reviewer=True)
    require_state(job, {"awaiting_review"})
    candidate = candidate_in(job, candidate_id)
    if job.mode == "ai":
        from .ai_services import source_valid

        source_valid(job)
        if values["decision"] == "approve" and not candidate.extraction.get("grounded"):
            raise ValidationError(
                "Ungrounded or unknown AI candidates cannot be approved; inspect "
                "the source manually."
            )
    expected = values.pop("expected_version")
    # A repeated identical request succeeds even with its pre-review version.
    normalized = candidate.normalized
    if values["decision"] == "approve" and ("value" in values or "unit" in values):
        normalized = normalize(
            candidate.field,
            values.get(
                "value", str(candidate.normalized.get("value", candidate.proposed["value"]))
            ),
            values.get(
                "unit", candidate.normalized.get("unit", candidate.proposed.get("unit", ""))
            ),
            job.created_at,
        )
    if values["decision"] == "approve" and (candidate.row.errors or not normalized):
        raise ValidationError(
            "Correct invalid candidates before approval; invalid rows require a new upload."
        )
    if values["select_value"] and candidate.field not in NUMERIC:
        raise ValidationError("Explicit claim selection applies to numeric claims only.")
    same = (
        candidate.decision == values["decision"]
        and candidate.reason == values["reason"]
        and candidate.select_value == values["select_value"]
        and candidate.normalized == normalized
    )
    if same:
        return candidate
    version(candidate, expected)
    before = {
        "normalized": candidate.normalized,
        "decision": candidate.decision,
        "quality": candidate.quality,
        "select_value": candidate.select_value,
    }
    candidate.normalized = normalized
    if normalized:
        candidate.existing, candidate.quality = comparison(
            candidate.row, candidate.field, normalized
        )
        candidate.errors = []
    candidate.decision, candidate.reason = values["decision"], values["reason"]
    candidate.select_value = values["select_value"]
    candidate.reviewed_by, candidate.reviewed_at = actor, timezone.now()
    candidate.version += 1
    candidate.save()
    ReviewRecord.objects.create(
        job=job,
        candidate=candidate,
        actor=actor,
        action=candidate.decision,
        reason=candidate.reason,
        before=before,
        after={
            "normalized": normalized,
            "decision": candidate.decision,
            "select_value": candidate.select_value,
        },
    )
    event(job, actor, "candidate_" + candidate.decision)
    annotate_competitors(job)
    candidate.refresh_from_db()
    save_job(job)
    if job.mode == "ai":
        job.counters.update(
            approved=Candidate.objects.filter(row__job=job, decision="approve").count(),
            rejected=Candidate.objects.filter(row__job=job, decision="reject").count(),
            awaiting_review=Candidate.objects.filter(row__job=job, decision="pending").count(),
        )
        job.save(update_fields=["counters"])
    return candidate


@transaction.atomic
def approve_creation(actor, org, job_id, row_id, values):
    job = job_in(actor, org, job_id, lock=True, reviewer=True)
    require_state(job, {"awaiting_review"})
    try:
        row = job.rows.get(pk=row_id)
    except ImportRow.DoesNotExist as error:
        raise NotFound("Import row not found.") from error
    if row.errors:
        raise ValidationError("Invalid rows cannot create products.")
    if row.allow_create != values["allow_create"]:
        row.allow_create = values["allow_create"]
        row.save()
        ReviewRecord.objects.create(
            job=job,
            row=row,
            actor=actor,
            action="creation_permission",
            reason=values["reason"],
            after={"allow_create": row.allow_create},
        )
        event(job, actor, "creation_reviewed")
        save_job(job)
    return row


@transaction.atomic
def refresh(actor, org, job_id, values):
    job = job_in(actor, org, job_id, lock=True, reviewer=True)
    version(job, values["expected_version"])
    require_state(job, {"awaiting_review"})
    for row in job.rows.all():
        row.product = Product.objects.filter(organization=job.organization, sku=row.sku).first()
        package_name = row.raw.get(job.mapping.get("package_name"), "").strip()
        row.packaging = (
            row.packaging
            if job.mode == "ai"
            else (
                row.product.configurations.filter(name=package_name).first()
                if row.product
                else None
            )
        )
        row.expected_revision = row.product.revisions.first().number if row.product else None
        row.expected_packaging_version = row.packaging.version if row.packaging else None
        row.save()
        for candidate in row.candidates.all():
            if candidate.normalized:
                candidate.existing, candidate.quality = comparison(
                    row, candidate.field, candidate.normalized
                )
            candidate.decision, candidate.reason, candidate.select_value = "pending", "", False
            candidate.version += 1
            candidate.save()
    ReviewRecord.objects.create(
        job=job,
        actor=actor,
        action="refresh",
        reason="Refresh targets and invalidate prior approvals",
    )
    event(job, actor, "refreshed")
    annotate_competitors(job)
    save_job(job)
    return job


def stale_targets(job):
    for row in job.rows.all():
        current = Product.objects.filter(organization=job.organization, sku=row.sku).first()
        if (current.pk if current else None) != row.product_id:
            raise catalog.Conflict("Catalog targets changed; refresh and review this import.")
        if current:
            catalog.require_active(current)
            if current.revisions.first().number != row.expected_revision:
                raise catalog.Conflict("Product changed; refresh and review this import.")
        if row.packaging_id and (
            not row.packaging.is_active or row.packaging.version != row.expected_packaging_version
        ):
            raise catalog.Conflict("Packaging changed; refresh and review this import.")
        for candidate in row.candidates.filter(decision="approve"):
            existing, _ = comparison(row, candidate.field, candidate.normalized)
            if existing != candidate.existing:
                raise catalog.Conflict("Evidence changed; refresh and review this import.")


@transaction.atomic
def apply(actor, org, job_id, values):
    job = job_in(actor, org, job_id, lock=True, reviewer=True)
    if job.status in {"completed", "completed_with_errors"}:
        return job
    version(job, values["expected_version"])
    require_state(job, {"awaiting_review"})
    if job.mode == "ai":
        from .ai_services import source_valid

        source_valid(job)
        for candidate in Candidate.objects.filter(row__job=job, decision="approve"):
            if not candidate.extraction.get("grounded"):
                raise ValidationError("Ungrounded AI values cannot be applied.")
            checked = normalize(
                candidate.field,
                str(candidate.normalized.get("value", "")),
                candidate.normalized.get("unit", ""),
                job.created_at,
            )
            if checked != candidate.normalized:
                raise ValidationError("Candidate normalization changed; review again.")
    if Candidate.objects.filter(row__job=job, decision="pending").exists():
        raise ValidationError("Approve or reject every candidate before applying the job.")
    stale_targets(job)
    decisions = {}
    for candidate in Candidate.objects.filter(row__job=job, decision="approve").select_related(
        "row"
    ):
        if candidate.field in NUMERIC and not candidate.select_value:
            continue
        package = candidate.row.raw.get(job.mapping.get("package_name"), "").strip()
        key = (
            candidate.row.sku,
            "" if candidate.field in PRODUCT_FIELDS else package,
            candidate.field,
        )
        normalized = candidate.normalized
        signature = (
            (Decimal(normalized["canonical_value"]), normalized["canonical_unit"])
            if candidate.field in NUMERIC
            else normalized["value"]
        )
        if key in decisions and decisions[key] != signature:
            raise ValidationError(
                "Competing approvals cannot overwrite each other. Choose one descriptor or "
                "canonical selection; retain other measurements without selection."
            )
        decisions[key] = signature
    counts = Counter()
    created_packages = set()
    selections = []
    measurement_scopes = set()
    for row in job.rows.all():
        approved = {c.field: c for c in row.candidates.filter(decision="approve")}
        counts["rejected_candidates"] += row.candidates.filter(decision="reject").count()
        if not approved or row.errors:
            counts["skipped_rows"] += 1
            continue
        fields = {
            field: c.normalized["value"] for field, c in approved.items() if field not in NUMERIC
        }
        product = Product.objects.filter(organization=job.organization, sku=row.sku).first()
        if not product:
            if not row.allow_create or not fields.get("name"):
                raise ValidationError(
                    "New products require explicit creation approval and an approved name."
                )
            product = catalog.create_product(
                actor,
                org,
                {
                    "sku": row.sku,
                    "revision": {
                        **{k: v for k, v in fields.items() if k in PRODUCT_FIELDS},
                        "change_reason": f"Approved import {job.pk}",
                    },
                },
            )
            counts["created_products"] += 1
        row.product = product
        # One immutable evidence record per applied row, linked to private bytes by the row.
        evidence = Evidence.objects.create(
            product=product,
            title=job.display_name,
            source_type="imported_catalog"
            if job.format in {"csv", "xlsx"}
            else "supplier_document",
            source_reference=f"import:{job.pk}:row:{row.pk}",
            description=(
                f"{row.location}; {job.parser_version}; SHA-256 {job.sha256}; "
                "reported, not physically verified"
            ),
            declared_sha256=job.sha256,
            attribution="Customer-provided upload; rights unverified",
            license="Unverified customer declaration",
            observed_at=job.created_at,
            recorded_by=actor,
        )
        row.evidence = evidence
        catalog.event("product.evidence_recorded", actor, product, evidence)
        edits = {
            k: v
            for k, v in fields.items()
            if k in PRODUCT_FIELDS and getattr(product.revisions.first(), k) != v
        }
        if edits:
            latest = product.revisions.first()
            snapshot = workflows.snapshot_input(latest)
            snapshot.update(edits)
            snapshot["change_reason"] = f"Approved import {job.pk} row {row.number}"
            snapshot["evidence_ids"].append(str(evidence.pk))
            catalog._append_revision(
                actor, product, catalog.validated(catalog.RevisionInput, snapshot)
            )
            counts["updated_products"] += 1
        else:
            # Append a source-linked snapshot; never mutate an existing revision's source set.
            snapshot = workflows.snapshot_input(product.revisions.first())
            snapshot["evidence_ids"].append(str(evidence.pk))
            snapshot["change_reason"] = f"Accepted evidence from import {job.pk} row {row.number}"
            catalog._append_revision(
                actor, product, catalog.validated(catalog.RevisionInput, snapshot)
            )
        packaging = row.packaging
        original_package = row.raw.get(job.mapping.get("package_name"), "").strip()
        if original_package and not fields.get("package_name"):
            raise ValidationError(
                "Package-scoped rows require approval of their package_name candidate."
            )
        if fields.get("package_name"):
            packaging = product.configurations.filter(name=fields["package_name"]).first()
            own_package = (product.pk, fields["package_name"]) in created_packages
            if (packaging.pk if packaging else None) != row.packaging_id and not own_package:
                raise catalog.Conflict(
                    "Package target changed; upload corrected source or refresh before review."
                )
            if not packaging:
                if not fields.get("package_type"):
                    raise ValidationError(
                        "A new package requires an approved name and package type."
                    )
                payload = {
                    "name": fields["package_name"],
                    "level": fields["package_type"],
                    **{k: fields[k] for k in ("quantity", "material") if k in fields},
                }
                packaging = workflows.create_configuration(
                    actor, org, product.pk, catalog.validated(ConfigurationInput, payload)
                )
                counts["created_packaging"] += 1
                created_packages.add((product.pk, fields["package_name"]))
        elif any(k in fields for k in {"package_type", "quantity", "material"}):
            raise ValidationError(
                "Packaging descriptors require an approved package_name candidate."
            )
        if packaging:
            edits = {
                attr: fields[field]
                for field, attr in (
                    ("package_type", "level"),
                    ("quantity", "quantity"),
                    ("material", "material"),
                )
                if field in fields and getattr(packaging, attr) != fields[field]
            }
            if edits:
                packaging = workflows.edit_configuration(
                    actor,
                    org,
                    product.pk,
                    packaging.pk,
                    {
                        **edits,
                        "expected_version": packaging.version,
                        "change_reason": f"Approved import {job.pk}",
                    },
                )
                counts["updated_packaging"] += 1
        for field, candidate in approved.items():
            if field not in NUMERIC:
                continue
            # Keep every source claim; equivalence grants neither verification nor selection.
            claim = workflows.create_claim(
                actor,
                org,
                product.pk,
                {
                    "attribute": field,
                    "basis": "reported",
                    "value": candidate.normalized["value"],
                    "unit": candidate.normalized["unit"],
                    "evidence_id": str(evidence.pk),
                    "observed_at": job.created_at,
                    "method": job.parser_version,
                    "limitations": (
                        "Imported source assertion; no physical verification. "
                        "Timestamp is upload/transcription time; source measurement date unknown."
                    ),
                },
                packaging_id=packaging.pk if packaging else None,
            )
            candidate.claim = claim
            candidate.save()
            measurement_scopes.add((product.pk, packaging.pk if packaging else None, field))
            if candidate.select_value:
                selections.append(
                    (
                        product.pk,
                        field,
                        claim.pk,
                        candidate.reason,
                        packaging.pk if packaging else None,
                    )
                )
            counts["created_claims"] += 1
        row.packaging, row.applied = packaging, True
        row.save()
        counts["applied_rows"] += 1
    for product_id, field, claim_id, reason, packaging_id in selections:
        workflows.select_claim(
            actor,
            org,
            product_id,
            field,
            {"claim_id": str(claim_id), "rationale": reason},
            packaging_id=packaging_id,
        )
    unresolved = 0
    for product_id, packaging_id, field in measurement_scopes:
        product = Product.objects.get(pk=product_id)
        packaging = workflows.configuration_in(product, packaging_id) if packaging_id else None
        state = next(
            s
            for s in workflows.attribute_states(product, packaging)["results"]
            if s["attribute"] == field
        )
        unresolved += bool(state["conflicting"] and state["selected_claim"] is None)
    counts["unresolved_conflicts"] = unresolved
    counts["rejected_rows"] = counts["skipped_rows"]
    job.counters.update(counts)
    job.counters["accepted_candidates"] = Candidate.objects.filter(
        row__job=job, decision="approve"
    ).count()
    job.status = (
        "completed_with_errors"
        if (counts["skipped_rows"] or counts["rejected_candidates"])
        else "completed"
    )
    job.completed_at = timezone.now()
    if job.mode == "ai":
        job.extraction["stage"] = job.status
    save_job(job)
    event(job, actor, "applied")
    return job


@transaction.atomic
def cancel(actor, org, job_id, values):
    job = job_in(actor, org, job_id, lock=True, reviewer=True)
    if job.status == "cancelled":
        return job
    version(job, values["expected_version"])
    require_state(
        job,
        {"uploaded", "failed", "awaiting_review", "processing"}
        if job.mode == "ai"
        else {"uploaded", "failed", "awaiting_review"},
    )
    job.status, job.completed_at = "cancelled", timezone.now()
    if job.mode == "ai":
        job.extraction.update(stage="cancelled", retryable=False)
    save_job(job)
    event(job, actor, "cancelled")
    return job
