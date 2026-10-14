from django.db import IntegrityError, transaction
from django.db.models import Max
from rest_framework.exceptions import APIException, NotFound, ValidationError

from audit.services import record
from organizations.services import ADMIN, OWNER, authorize

from .models import (
    Evidence,
    Measurement,
    PackagingProfile,
    Product,
    ProductRevision,
    RevisionEvidence,
)
from .serializers import (
    CONVERSIONS,
    LEVELS,
    EvidenceInput,
    ProductCreateInput,
    ProductStateInput,
    RevisionInput,
)


class Conflict(APIException):
    status_code = 409
    default_detail = "A product with this SKU already exists in the organization."


def validated(serializer_class, data):
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def products_in(organization):
    return Product.objects.filter(organization=organization).annotate(
        latest_revision_number=Max("revisions__number")
    )


def product_in(organization, product_id, *, lock=False):
    query = Product.objects.filter(organization=organization)
    if lock:
        query = query.select_for_update()
    try:
        return query.get(pk=product_id)
    except Product.DoesNotExist as error:
        raise NotFound("Product not found.") from error


def revisions_in(product):
    return product.revisions.prefetch_related("sources", "packaging__measurements")


def revision_in(product, revision_id):
    try:
        return revisions_in(product).get(pk=revision_id)
    except ProductRevision.DoesNotExist as error:
        raise NotFound("Revision not found.") from error


def evidence_in(product, evidence_id):
    try:
        return product.evidence.get(pk=evidence_id)
    except Evidence.DoesNotExist as error:
        raise NotFound("Evidence not found.") from error


def require_active(product):
    if not product.is_active:
        raise ValidationError("Archived products cannot receive new revisions or evidence.")


def event(action, actor, product, target):
    record(
        action,
        actor=actor,
        organization=product.organization,
        target_type=target._meta.model_name,
        target_id=target.pk,
    )


def _append_revision(actor, product, data):
    # The caller holds both the organization and product locks in the surrounding transaction.
    profiles = data.pop("packaging")
    references = set(data.pop("evidence_ids"))
    for profile in profiles:
        references.update(observation["evidence_id"] for observation in profile["measurements"])
    sources = {item.pk: item for item in product.evidence.filter(pk__in=references)}
    if set(sources) != references:
        raise NotFound("Evidence not found.")
    number = (product.revisions.aggregate(number=Max("number"))["number"] or 0) + 1
    revision = ProductRevision.objects.create(
        product=product, number=number, created_by=actor, **data
    )
    for source in sources.values():
        RevisionEvidence.objects.create(revision=revision, evidence=source)
    created = {}
    for profile in sorted(profiles, key=lambda item: LEVELS.index(item["level"])):
        observations = profile.pop("measurements")
        contained = profile.pop("contains_level")
        packaging = PackagingProfile.objects.create(
            revision=revision, contains=created.get(contained), **profile
        )
        created[packaging.level] = packaging
        for observation in observations:
            factor, unit = CONVERSIONS[observation["unit"]]
            value, lower, upper = (observation[key] for key in ("value", "lower", "upper"))
            Measurement.objects.create(
                packaging=packaging,
                property=observation["property"],
                original_value=value,
                original_unit=observation["unit"],
                original_lower=lower,
                original_upper=upper,
                canonical_value=value * factor,
                canonical_unit=unit,
                canonical_lower=None if lower is None else lower * factor,
                canonical_upper=None if upper is None else upper * factor,
                evidence=sources[observation["evidence_id"]],
                method=observation["method"],
                observed_at=observation["observed_at"],
            )
    event("product.revision_created", actor, product, revision)
    product.save(update_fields=["updated_at"])
    return revision_in(product, revision.pk)


@transaction.atomic
def create_product(actor, organization_id, data):
    organization, _ = authorize(actor, organization_id, lock=True)
    values = validated(ProductCreateInput, data)
    try:
        with transaction.atomic():
            product = Product.objects.create(organization=organization, sku=values["sku"])
    except IntegrityError as error:
        raise Conflict() from error
    event("product.created", actor, product, product)
    _append_revision(actor, product, values["revision"])
    return products_in(organization).get(pk=product.pk)


@transaction.atomic
def create_revision(actor, organization_id, product_id, data):
    organization, _ = authorize(actor, organization_id, lock=True)
    product = product_in(organization, product_id, lock=True)
    require_active(product)
    return _append_revision(actor, product, validated(RevisionInput, data))


@transaction.atomic
def create_evidence(actor, organization_id, product_id, data):
    organization, _ = authorize(actor, organization_id, lock=True)
    product = product_in(organization, product_id, lock=True)
    require_active(product)
    evidence = Evidence.objects.create(
        product=product, recorded_by=actor, **validated(EvidenceInput, data)
    )
    event("product.evidence_recorded", actor, product, evidence)
    return evidence


@transaction.atomic
def set_product_active(actor, organization_id, product_id, data):
    organization, _ = authorize(actor, organization_id, roles={OWNER, ADMIN}, lock=True)
    product = product_in(organization, product_id, lock=True)
    values = validated(ProductStateInput, data)
    if product.is_active != values["is_active"]:
        product.is_active = values["is_active"]
        product.save(update_fields=["is_active", "updated_at"])
        event(
            "product.reactivated" if product.is_active else "product.archived",
            actor,
            product,
            product,
        )
    return products_in(organization).get(pk=product.pk)
