from collections import defaultdict

from django.db import IntegrityError, transaction
from django.db.models import CharField, Q
from django.db.models.functions import Cast
from rest_framework.exceptions import NotFound, ValidationError

from audit.models import AuditEvent
from commercial import services as commercial
from organizations.services import ADMIN, OWNER, authorize

from . import services
from .models import (
    ATTRIBUTES,
    NUMERIC_ATTRIBUTES,
    AttributeClaim,
    ClaimSelection,
    ClaimVerification,
    ConfigurationRevision,
    Evidence,
    PackagingConfiguration,
)
from .serializers import CONVERSIONS, RevisionInput
from .workflow_serializers import (
    ClaimInput,
    ConfigurationEditInput,
    ConfigurationInput,
    ConfigurationStateInput,
    ProductEditInput,
    SelectionInput,
    VerificationInput,
)


class StaleWrite(services.Conflict):
    default_detail = "This record changed. Reload it before submitting your changes."


def configuration_in(product, packaging_id, *, lock=False):
    query = product.configurations.all()
    if lock:
        query = query.select_for_update()
    try:
        return query.get(pk=packaging_id)
    except PackagingConfiguration.DoesNotExist as error:
        raise NotFound("Packaging profile not found.") from error


def claims_in(product, packaging=None):
    return (
        AttributeClaim.objects.filter(product=product, packaging=packaging)
        .select_related("evidence", "verification_record")
        .prefetch_related("verifications")
    )


def claim_in(product, packaging, claim_id):
    try:
        return claims_in(product, packaging).get(pk=claim_id)
    except AttributeClaim.DoesNotExist as error:
        raise NotFound("Attribute claim not found.") from error


def writable(actor, organization_id, product_id, *, packaging_id=None, roles=None):
    organization, _ = authorize(actor, organization_id, roles=roles, lock=True)
    commercial.require(organization, "catalog_write")
    product = services.product_in(organization, product_id, lock=True)
    services.require_active(product)
    packaging = configuration_in(product, packaging_id, lock=True) if packaging_id else None
    if packaging is not None and not packaging.is_active:
        raise ValidationError("Archived packaging cannot receive changes, claims or verification.")
    return product, packaging


def workflow_event(action, actor, product, target):
    # Summaries contain fixed actions and resource IDs; customer text stays in domain records.
    services.event(action, actor, product, target)


def configuration_snapshot(packaging, actor, reason):
    values = {
        field: getattr(packaging, field)
        for field in [
            "version",
            "name",
            "level",
            "quantity",
            "material",
            "description",
            "is_active",
        ]
    }
    ConfigurationRevision.objects.create(
        packaging=packaging, changed_by=actor, change_reason=reason, **values
    )


def snapshot_input(revision):
    values = {
        field: getattr(revision, field)
        for field in [
            "name",
            "description",
            "brand",
            "manufacturer",
            "model_number",
            "category",
            "change_reason",
        ]
    }
    values["evidence_ids"] = [str(source.evidence_id) for source in revision.sources.all()]
    profiles = list(revision.packaging.all())
    levels = {profile.pk: profile.level for profile in profiles}
    values["packaging"] = []
    for profile in profiles:
        item = {
            field: getattr(profile, field)
            for field in ["level", "quantity", "material", "notes", "fragile", "stackable"]
        }
        item["contains_level"] = levels.get(profile.contains_id)
        item["measurements"] = [
            {
                "property": observation.property,
                "value": str(observation.original_value),
                "unit": observation.original_unit,
                "lower": None
                if observation.original_lower is None
                else str(observation.original_lower),
                "upper": None
                if observation.original_upper is None
                else str(observation.original_upper),
                "method": observation.method,
                "observed_at": observation.observed_at,
                "evidence_id": str(observation.evidence_id),
            }
            for observation in profile.measurements.all()
        ]
        values["packaging"].append(item)
    return values


@transaction.atomic
def edit_product(actor, organization_id, product_id, data):
    product, _ = writable(actor, organization_id, product_id)
    values = services.validated(ProductEditInput, data)
    latest = services.revisions_in(product).first()
    if latest.number != values.pop("expected_revision"):
        raise StaleWrite()
    payload = snapshot_input(latest)
    payload.update(values)
    services._append_revision(actor, product, services.validated(RevisionInput, payload))
    workflow_event("product.updated", actor, product, product)
    return services.products_in(product.organization).get(pk=product.pk)


@transaction.atomic
def create_configuration(actor, organization_id, product_id, data):
    product, _ = writable(actor, organization_id, product_id)
    values = services.validated(ConfigurationInput, data)
    try:
        with transaction.atomic():
            packaging = PackagingConfiguration.objects.create(
                product=product, created_by=actor, modified_by=actor, **values
            )
    except IntegrityError as error:
        raise services.Conflict(
            "A packaging profile with this name already exists for the product."
        ) from error
    configuration_snapshot(packaging, actor, "Initial packaging profile")
    workflow_event("packaging.created", actor, product, packaging)
    return packaging


@transaction.atomic
def edit_configuration(actor, organization_id, product_id, packaging_id, data):
    product, packaging = writable(actor, organization_id, product_id, packaging_id=packaging_id)
    values = services.validated(ConfigurationEditInput, data)
    if packaging.version != values.pop("expected_version"):
        raise StaleWrite()
    reason = values.pop("change_reason")
    for field, value in values.items():
        setattr(packaging, field, value)
    packaging.version += 1
    packaging.modified_by = actor
    try:
        with transaction.atomic():
            packaging.save()
    except IntegrityError as error:
        raise services.Conflict(
            "A packaging profile with this name already exists for the product."
        ) from error
    configuration_snapshot(packaging, actor, reason)
    workflow_event("packaging.updated", actor, product, packaging)
    return packaging


@transaction.atomic
def configuration_state(actor, organization_id, product_id, packaging_id, data):
    organization, _ = authorize(actor, organization_id, roles={OWNER, ADMIN}, lock=True)
    product = services.product_in(organization, product_id, lock=True)
    services.require_active(product)
    packaging = configuration_in(product, packaging_id, lock=True)
    values = services.validated(ConfigurationStateInput, data)
    if packaging.version != values["expected_version"]:
        raise StaleWrite()
    if packaging.is_active != values["is_active"]:
        if values["is_active"]:
            commercial.require(organization, "catalog_write")
        packaging.is_active = values["is_active"]
        packaging.version += 1
        packaging.modified_by = actor
        packaging.save()
        configuration_snapshot(
            packaging,
            actor,
            "Reactivated packaging" if packaging.is_active else "Archived packaging",
        )
        workflow_event(
            "packaging.reactivated" if packaging.is_active else "packaging.archived",
            actor,
            product,
            packaging,
        )
    return packaging


def canonical_fields(values):
    if values["attribute"] not in NUMERIC_ATTRIBUTES:
        return {
            "canonical_value": None,
            "canonical_unit": "",
            "canonical_lower": None,
            "canonical_upper": None,
        }
    factor, unit = CONVERSIONS[values["unit"]]
    return {
        "canonical_value": values["value"] * factor,
        "canonical_unit": unit,
        "canonical_lower": None if values["lower"] is None else values["lower"] * factor,
        "canonical_upper": None if values["upper"] is None else values["upper"] * factor,
    }


def _source(actor, product, values):
    source = values.pop("source", None)
    if source is not None:
        evidence = Evidence.objects.create(product=product, recorded_by=actor, **source)
        workflow_event("product.evidence_recorded", actor, product, evidence)
        return evidence
    return services.evidence_in(product, values.pop("evidence_id"))


def _claim(actor, product, packaging, values, *, measured=False):
    evidence = _source(actor, product, values)
    if evidence.source_type == "ai_estimate" and values["basis"] != "estimated":
        raise ValidationError("AI source references can support estimates only.")
    if claims_in(product, packaging).count() >= 500:
        raise ValidationError(
            "This resource has reached the 500-claim limit. "
            "Retain history and contact an administrator."
        )
    claim = AttributeClaim.objects.create(
        product=product,
        packaging=packaging,
        evidence=evidence,
        recorded_by=actor,
        **canonical_fields(values),
        **values,
    )
    if not measured:
        workflow_event(
            "evidence.claim_reported" if claim.basis == "reported" else "evidence.claim_estimated",
            actor,
            product,
            claim,
        )
    return claim


@transaction.atomic
def create_claim(actor, organization_id, product_id, data, *, packaging_id=None):
    product, packaging = writable(actor, organization_id, product_id, packaging_id=packaging_id)
    values = services.validated(ClaimInput, data)
    claim = _claim(actor, product, packaging, values)
    return claim_in(product, packaging, claim.pk)


@transaction.atomic
def verify_claim(actor, organization_id, product_id, claim_id, data, *, packaging_id=None):
    product, packaging = writable(
        actor, organization_id, product_id, packaging_id=packaging_id, roles={OWNER, ADMIN}
    )
    claim = claim_in(product, packaging, claim_id)
    if claim.attribute not in NUMERIC_ATTRIBUTES:
        raise ValidationError(
            "Physical verification requires a numeric dimension or mass attribute."
        )
    values = services.validated(VerificationInput, data)
    source = _source(actor, product, values)
    if source.source_type != "physical_test":
        raise ValidationError(
            "Verification requires a physical_test source and documented measurement procedure."
        )
    instrument, procedure, notes = (
        values.pop(field) for field in ["instrument", "procedure", "notes"]
    )
    payload = {
        "evidence_id": source.pk,
        **values,
        "attribute": claim.attribute,
        "basis": "reported",
        "method": procedure,
        "limitations": notes,
    }
    checked = services.validated(ClaimInput, payload)
    checked["basis"] = "measured"
    measured = _claim(actor, product, packaging, checked, measured=True)
    verification = ClaimVerification.objects.create(
        claim=claim,
        measured_claim=measured,
        verified_by=actor,
        instrument=instrument,
        procedure=procedure,
        notes=notes,
    )
    workflow_event("evidence.physically_verified", actor, product, verification)
    return claim_in(product, packaging, measured.pk)


@transaction.atomic
def select_claim(actor, organization_id, product_id, attribute, data, *, packaging_id=None):
    product, packaging = writable(
        actor, organization_id, product_id, packaging_id=packaging_id, roles={OWNER, ADMIN}
    )
    if attribute not in ATTRIBUTES:
        raise NotFound("Attribute not found.")
    values = services.validated(SelectionInput, data)
    claim = claim_in(product, packaging, values["claim_id"])
    if claim.attribute != attribute:
        raise ValidationError("The selected claim must describe this attribute.")
    selection = ClaimSelection.objects.create(
        claim=claim, selected_by=actor, rationale=values["rationale"]
    )
    workflow_event("evidence.claim_selected", actor, product, selection)
    return selection


def attribute_states(product, packaging=None):
    def signature(claim):
        return (
            claim.canonical_value,
            claim.canonical_unit,
            claim.canonical_lower,
            claim.canonical_upper,
            claim.text_value,
        )

    grouped = defaultdict(list)
    for claim in claims_in(product, packaging):
        grouped[claim.attribute].append(claim)
    results = []
    for attribute in ATTRIBUTES:
        claims = grouped[attribute]
        signatures = {signature(claim) for claim in claims}
        conflict = len(signatures) > 1
        selection = (
            ClaimSelection.objects.filter(
                claim__product=product, claim__packaging=packaging, claim__attribute=attribute
            )
            .select_related("claim")
            .first()
        )
        stale = (
            selection
            and conflict
            and any(
                claim.recorded_at > selection.selected_at
                and signature(claim) != signature(selection.claim)
                for claim in claims
            )
        )
        selected = (
            None
            if not selection or stale
            else next((c for c in claims if c.pk == selection.claim_id), None)
        )
        status = (
            "unknown"
            if not claims
            else "conflict"
            if conflict
            else "verified"
            if any(c.basis == "measured" for c in claims)
            else claims[0].basis
        )
        if selected is not None:
            status = "resolved" if conflict else status
        results.append(
            {
                "attribute": attribute,
                "status": status,
                "claim_count": len(claims),
                "conflicting": conflict,
                "selected_claim": selected,
                "selection": selection,
            }
        )
    return {"results": results}


def history_in(product, packaging=None):
    def identifiers(query):
        return query.annotate(history_id=Cast("pk", CharField())).values("history_id")

    claims = AttributeClaim.objects.filter(product=product)
    if packaging is not None:
        claims = claims.filter(packaging=packaging)
        query = Q(target_type="packagingconfiguration", target_id=str(packaging.pk))
    else:
        query = Q(target_type="product", target_id=str(product.pk))
        query |= Q(
            target_type="productrevision", target_id__in=identifiers(product.revisions.all())
        )
        query |= Q(target_type="evidence", target_id__in=identifiers(product.evidence.all()))
        query |= Q(
            target_type="packagingconfiguration",
            target_id__in=identifiers(product.configurations.all()),
        )
    query |= Q(target_type="attributeclaim", target_id__in=identifiers(claims))
    query |= Q(
        target_type="claimverification",
        target_id__in=identifiers(ClaimVerification.objects.filter(claim__in=claims)),
    )
    query |= Q(
        target_type="claimselection",
        target_id__in=identifiers(ClaimSelection.objects.filter(claim__in=claims)),
    )
    return AuditEvent.objects.filter(query, organization=product.organization, outcome="success")
