import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from audit.services import record
from commercial import services as commercial
from ingestion.models import ImportJob
from organizations.services import ADMIN, OWNER, authorize
from products import services as catalog
from products import workflows
from products.models import Evidence
from products.serializers import EvidenceSerializer, ProductSerializer
from products.workflow_serializers import (
    ClaimSerializer,
    ConfigurationSerializer,
    SelectionSerializer,
)

from . import engine
from .models import Assessment, Equipment, EquipmentRevision, RuleActivation, RuleSet
from .serializers import (
    ActivationInput,
    AssessmentInput,
    DefinitionInput,
    EquipmentEdit,
    EquipmentInput,
    EquipmentRevisionSerializer,
    EquipmentState,
    RuleSetInput,
    RuleSetSerializer,
)

MANAGERS = {OWNER, ADMIN}


def freeze(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True))


def event(actor, org, action, target):
    record(
        action,
        actor=actor,
        organization=org,
        target_type=target._meta.model_name,
        target_id=target.pk,
    )


def equipment_in(org):
    latest = EquipmentRevision.objects.filter(equipment=OuterRef("pk")).order_by("-number")
    rules = RuleSet.objects.filter(equipment=OuterRef("pk")).order_by("-number")
    return Equipment.objects.filter(organization=org).annotate(
        revision=Subquery(latest.values("number")[:1]),
        revision_id=Subquery(latest.values("id")[:1]),
        definition=Subquery(latest.values("definition")[:1]),
        latest_rule_version=Subquery(rules.values("number")[:1]),
    )


def equipment_get(org, pk):
    try:
        return equipment_in(org).get(pk=pk)
    except Equipment.DoesNotExist as error:
        raise NotFound("Equipment not found.") from error


def rule_get(equipment, pk):
    try:
        return equipment.rule_sets.select_related("equipment_revision", "activation").get(pk=pk)
    except RuleSet.DoesNotExist as error:
        raise NotFound("Rule set not found.") from error


def assessment_get(org, pk):
    try:
        return Assessment.objects.get(organization=org, pk=pk)
    except Assessment.DoesNotExist as error:
        raise NotFound("Assessment not found.") from error


def expected(actual, value):
    if actual != value:
        raise catalog.Conflict("This definition changed. Reload before continuing.")


@transaction.atomic
def create_equipment(actor, org_id, data):
    org, _ = authorize(actor, org_id, roles=MANAGERS, lock=True)
    commercial.require(org, "equipment_write")
    values = catalog.validated(EquipmentInput, data)
    code = values.pop("code")
    try:
        with transaction.atomic():
            equipment = Equipment.objects.create(
                organization=org, code=code, created_by=actor, modified_by=actor
            )
    except IntegrityError as error:
        raise catalog.Conflict("Equipment code already exists in this organization.") from error
    EquipmentRevision.objects.create(
        equipment=equipment,
        number=1,
        definition=freeze(values),
        reason="Initial equipment specification",
        created_by=actor,
    )
    event(actor, org, "equipment.created", equipment)
    return equipment_get(org, equipment.pk)


@transaction.atomic
def edit_equipment(actor, org_id, equipment_id, data):
    org, _ = authorize(actor, org_id, roles=MANAGERS, lock=True)
    commercial.require(org, "equipment_write")
    equipment = equipment_get(org, equipment_id)
    if equipment.status == "archived":
        raise ValidationError("Restore equipment to draft before editing.")
    values = catalog.validated(EquipmentEdit, data)
    expected(equipment.version, values.pop("expected_version"))
    reason = values.pop("reason")
    definition = catalog.validated(DefinitionInput, {**equipment.definition, **values})
    EquipmentRevision.objects.create(
        equipment=equipment,
        number=equipment.revision + 1,
        definition=freeze(definition),
        reason=reason,
        created_by=actor,
    )
    equipment.status, equipment.modified_by = "draft", actor
    equipment.version += 1
    equipment.save()
    event(actor, org, "equipment.revised", equipment)
    return equipment_get(org, equipment.pk)


@transaction.atomic
def equipment_state(actor, org_id, equipment_id, data):
    org, _ = authorize(actor, org_id, roles=MANAGERS, lock=True)
    equipment = equipment_get(org, equipment_id)
    values = catalog.validated(EquipmentState, data)
    if values["status"] != "archived":
        commercial.require(org, "equipment_write")
    expected(equipment.version, values["expected_version"])
    if equipment.status != values["status"]:
        equipment.status, equipment.modified_by = values["status"], actor
        equipment.version += 1
        equipment.save()
        event(actor, org, "equipment." + equipment.status, equipment)
        # Retain the reason in specification history; audit metadata stays fixed IDs.
        EquipmentRevision.objects.create(
            equipment=equipment,
            number=equipment.revision + 1,
            definition=equipment.definition,
            reason=values["reason"],
            created_by=actor,
        )
    return equipment_get(org, equipment.pk)


def source_snapshot(org, source):
    if not source:
        return None
    if source["kind"] == "evidence":
        item = Evidence.objects.filter(product__organization=org, pk=source["id"]).first()
        if item is None:
            raise NotFound("Specification source not found.")
        return {
            "kind": "evidence",
            "id": str(item.pk),
            "snapshot": freeze(EvidenceSerializer(item).data),
        }
    item = ImportJob.objects.filter(organization=org, pk=source["id"]).first()
    if item is None:
        raise NotFound("Specification source not found.")
    return {
        "kind": "import",
        "id": str(item.pk),
        "snapshot": {
            "name": item.display_name,
            "sha256": item.sha256,
            "scan_status": item.scan_status,
            "format": item.format,
            "download_path": f"/api/v1/organizations/{org.pk}/imports/{item.pk}/file/",
        },
    }


@transaction.atomic
def create_rules(actor, org_id, equipment_id, data):
    org, _ = authorize(actor, org_id, roles=MANAGERS, lock=True)
    commercial.require(org, "equipment_write")
    equipment = equipment_get(org, equipment_id)
    if equipment.status == "archived":
        raise ValidationError("Archived equipment cannot receive rules.")
    values = catalog.validated(RuleSetInput, data)
    expected(equipment.version, values.pop("expected_equipment_version"))
    previous = equipment.rule_sets.first()
    expected(previous.number if previous else 0, values.pop("expected_rule_version"))
    number = (previous.number if previous else 0) + 1
    old = {r["id"]: r for r in previous.rules} if previous else {}
    rules = []
    at = timezone.now().isoformat()
    for rule in values.pop("rules"):
        rule_id = str(rule["id"])
        prior = old.get(rule_id, {})
        rules.append(
            {
                **freeze(rule),
                "version": number,
                "source": source_snapshot(org, rule["source"]),
                "created_by_id": prior.get("created_by_id", actor.pk),
                "created_at": prior.get("created_at", at),
                "updated_by_id": actor.pk,
                "updated_at": at,
            }
        )
    result = RuleSet.objects.create(
        equipment=equipment,
        equipment_revision=equipment.revisions.first(),
        number=number,
        rules=rules,
        created_by=actor,
        **values,
    )
    event(actor, org, "equipment.rules_revised", result)
    return rule_get(equipment, result.pk)


@transaction.atomic
def activate(actor, org_id, equipment_id, rule_id, data):
    org, _ = authorize(actor, org_id, roles=MANAGERS, lock=True)
    commercial.require(org, "equipment_write")
    equipment = equipment_get(org, equipment_id)
    rules = rule_get(equipment, rule_id)
    values = catalog.validated(ActivationInput, data)
    if (
        equipment.status == "archived"
        or rules.equipment_revision_id != equipment.revisions.first().pk
    ):
        raise ValidationError(
            "Only rules for the current, nonarchived specification may be activated."
        )
    definition = equipment.definition
    if not definition["supported_levels"] or not definition["operational_context"]:
        raise ValidationError(
            "Document supported packaging levels and operational context before activation."
        )
    enabled = [r for r in rules.rules if r["enabled"]]
    if not any(r["severity"] == "hard" for r in enabled) or any(
        not r["source_reference"] and not r["source"] for r in enabled
    ):
        raise ValidationError(
            "Activation requires an enabled hard rule and provenance for every enabled rule."
        )
    if any(
        r.get("source")
        and r["source"]["kind"] == "evidence"
        and r["source"]["snapshot"]["source_type"] == "ai_estimate"
        for r in enabled
    ):
        raise ValidationError(
            "AI-estimate sources cannot establish documented equipment constraints."
        )
    if hasattr(rules, "activation") and equipment.status == "active":
        return rules
    expected(equipment.version, values["expected_equipment_version"])
    if not hasattr(rules, "activation"):
        RuleActivation.objects.create(rule_set=rules, activated_by=actor, reason=values["reason"])
    equipment.status, equipment.modified_by = "active", actor
    equipment.version += 1
    equipment.save()
    event(actor, org, "equipment.rules_activated", rules)
    return rule_get(equipment, rules.pk)


def input_snapshot(org, product, packaging, values):
    claims = workflows.claims_in(product, packaging).filter(attribute__in=engine.ATTRIBUTES)
    if claims.count() > 100:
        raise ValidationError(
            "Assessment scope exceeds 100 numeric claims; review history before evaluating."
        )
    serialized = freeze(ClaimSerializer(claims, many=True).data)
    states = workflows.attribute_states(product, packaging)["results"]
    attributes = {
        state["attribute"]: {
            "claims": [c for c in serialized if c["attribute"] == state["attribute"]],
            "conflicting": state["conflicting"],
            "quality_status": state["status"],
            "selected_claim_id": str(state["selected_claim"].pk)
            if state["selected_claim"]
            else None,
            "selection": freeze(SelectionSerializer(state["selection"]).data)
            if state["selection"]
            else None,
        }
        for state in states
        if state["attribute"] in engine.ATTRIBUTES
    }
    return {
        "product": freeze(ProductSerializer(catalog.products_in(org).get(pk=product.pk)).data),
        "packaging": freeze(ConfigurationSerializer(packaging).data) if packaging else None,
        "orientation": values["orientation"],
        "handling_level": packaging.level if packaging else values["product_level"],
        "level_basis": "reported_profile"
        if packaging
        else "explicit_assessment_context"
        if values["product_level"]
        else "unknown",
        "attributes": attributes,
    }


@transaction.atomic
def assess(actor, org_id, data):
    org, _ = authorize(actor, org_id, lock=True)
    values = catalog.validated(AssessmentInput, data)
    digest = hashlib.sha256(json.dumps(freeze(values), sort_keys=True).encode()).hexdigest()
    old = Assessment.objects.filter(organization=org, request_id=values["request_id"]).first()
    if old:
        if old.request_sha256 != digest:
            raise catalog.Conflict("Request identifier was used for different assessment operands.")
        return old
    commercial.reserve(org, "assessments", values["request_id"], digest)
    product = catalog.product_in(org, values["product_id"])
    catalog.require_active(product)
    packaging = (
        workflows.configuration_in(product, values["packaging_id"])
        if values["packaging_id"]
        else None
    )
    if packaging and not packaging.is_active:
        raise ValidationError("Archived packaging cannot be newly assessed.")
    equipment = equipment_get(org, values["equipment_id"])
    rules = rule_get(equipment, values["rule_set_id"])
    if (
        equipment.status != "active"
        or not hasattr(rules, "activation")
        or rules.equipment_revision_id != equipment.revisions.first().pk
    ):
        raise ValidationError(
            "Select active equipment and an activated rule set for its current specification."
        )
    parent = assessment_get(org, values["parent_id"]) if values["parent_id"] else None
    if parent and (
        parent.product_id != product.pk
        or parent.packaging_id != (packaging.pk if packaging else None)
        or parent.equipment_id != equipment.pk
    ):
        raise ValidationError(
            "A previous assessment must have the same product, package scope and equipment."
        )
    inputs = input_snapshot(org, product, packaging, values)
    equipment_snapshot = freeze(EquipmentRevisionSerializer(equipment.revisions.first()).data)
    rule_snapshot = freeze(RuleSetSerializer(rules).data)
    overall, summary, results = engine.evaluate(inputs, equipment_snapshot, rule_snapshot)
    assessment = Assessment.objects.create(
        organization=org,
        product=product,
        product_revision=product.revisions.first(),
        packaging=packaging,
        packaging_revision=packaging.revisions.first() if packaging else None,
        equipment=equipment,
        equipment_revision=rules.equipment_revision,
        rule_set=rules,
        parent=parent,
        request_id=values["request_id"],
        request_sha256=digest,
        created_by=actor,
        overall=overall,
        summary=summary,
        inputs=inputs,
        equipment_snapshot=equipment_snapshot,
        rule_snapshot=rule_snapshot,
        results=freeze(results),
    )
    event(actor, org, "assessment.created", assessment)
    commercial.finalize(org, "assessments", values["request_id"], actor)
    return assessment


def compare(org, first_id, second_id):
    first, second = assessment_get(org, first_id), assessment_get(org, second_id)
    if (first.product_id, first.packaging_id, first.equipment_id) != (
        second.product_id,
        second.packaging_id,
        second.equipment_id,
    ):
        raise ValidationError("Compare only the same product, package scope and equipment.")
    before = {row["rule_id"]: row for row in first.results}
    after = {row["rule_id"]: row for row in second.results}
    return {
        "first_id": str(first.pk),
        "second_id": str(second.pk),
        "first_result": first.overall,
        "second_result": second.overall,
        "changes": [
            {"rule_id": pk, "before": before.get(pk), "after": after.get(pk)}
            for pk in sorted(before.keys() | after.keys())
            if before.get(pk) != after.get(pk)
        ],
    }
