import copy
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.test import APIClient

from audit.models import AuditEvent
from organizations.models import Membership
from organizations.services import create_organization
from products import services as catalog
from products import workflows
from products.models import AttributeClaim

from . import engine, services
from .models import Assessment, Equipment
from .serializers import AssessmentInput, RuleInput


def definition(code="CONVEYOR-01"):
    return {
        "code": code,
        "name": "Documented conveyor",
        "category": "conveyor",
        "operational_context": "Recorded carton geometry and static mass envelope only",
        "supported_levels": ["unit", "case"],
        "source_reference": "Fixture manual section 4",
    }


def rule(attribute="length", limit="100", unit="mm", kind="maximum", **changes):
    return {
        "id": str(uuid.uuid4()),
        "type": kind,
        "name": f"{kind} {attribute}",
        "explanation": "Fixture documented inclusive constraint",
        "severity": "hard",
        "enabled": True,
        "attribute": attribute,
        "limit": limit,
        "unit": unit,
        "margin": "0",
        "source_reference": "Fixture manual section 4",
        **changes,
    }


def claim(value="10", unit="mm", basis="reported", **changes):
    factor, canonical = catalog.CONVERSIONS[unit]
    return {
        "id": str(uuid.uuid4()),
        "value": value,
        "unit": unit,
        "basis": basis,
        "canonical_value": str(Decimal(value) * factor),
        "canonical_unit": canonical,
        "lower": None,
        "upper": None,
        "canonical_lower": None,
        "canonical_upper": None,
        "verification_record": {"verified_by_id": 1} if basis == "measured" else None,
        **changes,
    }


class EngineTests(TestCase):
    def setUp(self):
        self.inputs = {
            "handling_level": "case",
            "orientation": "as_recorded",
            "attributes": {
                a: {"claims": [claim("1", "kg") if a == "mass" else claim()], "conflicting": False}
                for a in engine.ATTRIBUTES
            },
        }
        self.equipment = {"definition": {"supported_levels": ["unit", "case"]}}
        self.rules = [
            services.freeze(
                catalog.validated(
                    RuleInput, rule(a, "2" if a == "mass" else "100", "kg" if a == "mass" else "mm")
                )
            )
            for a in engine.ATTRIBUTES
        ]
        for r in self.rules:
            r["version"] = 1
        self.ruleset = {"number": 1, "evidence_policy": "reported_or_measured", "rules": self.rules}

    def evaluate(self):
        return engine.evaluate(self.inputs, self.equipment, self.ruleset)

    def test_all_maximum_rules_pass_deterministically(self):
        first = self.evaluate()
        self.assertEqual(first[0], "compatible")
        self.assertEqual(first, self.evaluate())
        self.assertIn("Not physical validation", first[1])

    def test_exact_inside_and_outside_boundaries(self):
        for value, expected in [
            ("99.999999", "compatible"),
            ("100", "compatible"),
            ("100.000001", "incompatible"),
        ]:
            with self.subTest(value=value):
                self.inputs["attributes"]["length"]["claims"] = [claim(value)]
                self.assertEqual(self.evaluate()[0], expected)

    def test_minimum_and_clearance_are_inclusive_and_directional(self):
        minimum = services.freeze(
            catalog.validated(RuleInput, rule(kind="minimum", limit="10", margin="1"))
        )
        minimum["version"] = 1
        self.rules.append(minimum)
        for value, expected in [
            ("10.999999", "incompatible"),
            ("11", "compatible"),
            ("11.000001", "compatible"),
        ]:
            self.inputs["attributes"]["length"]["claims"] = [claim(value)]
            self.assertEqual(self.evaluate()[0], expected)
        self.rules.pop()
        self.rules[0].update(margin="1", canonical_margin="1")
        self.inputs["attributes"]["length"]["claims"] = [claim("99")]
        self.assertEqual(self.evaluate()[0], "compatible")
        self.inputs["attributes"]["length"]["claims"] = [claim("99.000001")]
        self.assertEqual(self.evaluate()[0], "incompatible")

    def test_equivalent_metric_units_do_not_change_result(self):
        self.inputs["attributes"]["length"]["claims"] = [claim("0.1", "m")]
        self.inputs["attributes"]["mass"]["claims"] = [claim("2000", "g")]
        self.assertEqual(self.evaluate()[0], "compatible")

    def test_uncertainty_overlap_is_indeterminate_not_a_nominal_pass(self):
        c = claim("100", lower="99", upper="101", canonical_lower="99", canonical_upper="101")
        self.inputs["attributes"]["length"]["claims"] = [c]
        self.assertEqual(self.evaluate()[0], "indeterminate")
        c.update(
            value="102",
            canonical_value="102",
            lower="101",
            upper="103",
            canonical_lower="101",
            canonical_upper="103",
        )
        self.assertEqual(self.evaluate()[0], "incompatible")

    def test_missing_estimated_and_unbacked_measured_inputs_cannot_pass(self):
        for claims in [
            [],
            [claim(basis="estimated")],
            [claim(basis="measured", verification_record=None)],
        ]:
            self.inputs["attributes"]["length"]["claims"] = claims
            self.assertEqual(self.evaluate()[0], "indeterminate")
        self.inputs["attributes"]["length"]["claims"] = [claim()]
        self.ruleset["evidence_policy"] = "measured_only"
        self.assertEqual(self.evaluate()[0], "indeterminate")
        for state in self.inputs["attributes"].values():
            for c in state["claims"]:
                c.update(basis="measured", verification_record={"verified_by_id": 1})
        self.assertEqual(self.evaluate()[0], "compatible")

    def test_conflict_cannot_use_favorable_selected_value_but_all_failures_are_reliable(self):
        state = self.inputs["attributes"]["length"]
        state.update(
            claims=[claim("10"), claim("110")], conflicting=True, selected_claim_id="favorable"
        )
        self.assertEqual(self.evaluate()[0], "indeterminate")
        state["claims"] = [claim("101"), claim("110")]
        self.assertEqual(self.evaluate()[0], "incompatible")

    def test_hard_failure_precedes_unknowns_and_reports_all_failed_checks(self):
        self.inputs["attributes"]["length"]["claims"] = []
        self.inputs["attributes"]["width"]["claims"] = [claim("101")]
        self.inputs["attributes"]["mass"]["claims"] = [claim("3", "kg")]
        overall, _, rows = self.evaluate()
        self.assertEqual(overall, "incompatible")
        self.assertEqual(sum(r["status"] == "fail" for r in rows), 2)
        self.assertTrue(any(r["status"] == "indeterminate" for r in rows))

    def test_unknown_specification_or_empty_disabled_rules_never_implies_unlimited(self):
        self.ruleset["rules"] = []
        self.assertEqual(self.evaluate()[0], "indeterminate")
        self.ruleset["rules"] = self.rules
        self.rules[0]["enabled"] = False
        self.assertEqual(self.evaluate()[0], "indeterminate")
        self.assertTrue(any(r["status"] == "not_applicable" for r in self.evaluate()[2]))

    def test_required_attribute_packaging_and_orientation_types(self):
        additions = [
            {"type": "required_attribute", "attribute": "mass"},
            {"type": "packaging_level", "allowed": ["case"]},
            {"type": "orientation", "allowed": ["as_recorded"]},
        ]
        for part in additions:
            base = {
                "id": str(uuid.uuid4()),
                "name": "Explicit requirement",
                "explanation": "Documented requirement",
                "severity": "hard",
                "enabled": True,
                **part,
            }
            r = services.freeze(catalog.validated(RuleInput, base))
            r["version"] = 1
            self.rules.append(r)
        self.assertEqual(self.evaluate()[0], "compatible")
        self.inputs["orientation"] = "swap_length_width"
        self.assertEqual(self.evaluate()[0], "incompatible")
        self.inputs["orientation"] = None
        self.assertEqual(self.evaluate()[0], "indeterminate")
        self.inputs["handling_level"] = "pallet"
        self.assertEqual(self.evaluate()[0], "incompatible")

    def test_orientation_swaps_only_explicit_horizontal_axes(self):
        self.inputs["attributes"]["length"]["claims"] = [claim("90")]
        self.inputs["attributes"]["width"]["claims"] = [claim("10")]
        self.rules[0].update(limit="20", canonical_limit="20")
        self.assertEqual(self.evaluate()[0], "incompatible")
        self.inputs["orientation"] = "swap_length_width"
        self.assertEqual(self.evaluate()[0], "compatible")

    def test_malformed_nan_unknown_units_and_executable_types_fail_closed(self):
        for bad in [
            claim(value="1", unit="mm", canonical_value="NaN"),
            claim(unit="mm", unit_override="invalid"),
        ]:
            if "unit_override" in bad:
                bad["unit"] = bad.pop("unit_override")
            self.inputs["attributes"]["length"]["claims"] = [bad]
            self.assertEqual(self.evaluate()[0], "indeterminate")
        self.rules[0]["type"] = "__import__('os').system('ignored')"
        self.assertEqual(self.evaluate()[0], "indeterminate")

    def test_advisory_failure_is_explained_without_hard_incompatibility(self):
        warning = copy.deepcopy(self.rules[0])
        warning.update(id=str(uuid.uuid4()), limit="1", canonical_limit="1", severity="advisory")
        self.rules.append(warning)
        self.assertEqual(self.evaluate()[0], "compatible")
        self.assertEqual(self.evaluate()[2][-1]["status"], "fail")


class Fixture:
    def setup_fixture(self):
        cache.clear()
        self.owner = get_user_model().objects.create_user(
            "equipment-owner", password="Local-only-password!2026"
        )
        self.member = get_user_model().objects.create_user("equipment-member")
        self.outsider = get_user_model().objects.create_user("equipment-outsider")
        self.org = create_organization(self.owner, name="Equipment lab", slug="equipment-lab")
        self.other = create_organization(
            self.outsider, name="Other equipment", slug="equipment-other"
        )
        Membership.objects.create(user=self.member, organization=self.org, role="member")
        self.product = catalog.create_product(
            self.owner,
            self.org.pk,
            {"sku": "FIT-001", "revision": {"name": "Fixture carton", "change_reason": "Initial"}},
        )
        self.pack = workflows.create_configuration(
            self.owner, self.org.pk, self.product.pk, {"name": "Shipping case", "level": "case"}
        )
        self.evidence = catalog.create_evidence(
            self.owner,
            self.org.pk,
            self.product.pk,
            {
                "title": "Supplier record",
                "source_type": "supplier_document",
                "source_reference": "Fixture sheet 2",
                "attribution": "Fixture supplier",
                "license": "Internal test",
                "observed_at": timezone.now(),
            },
        )
        for a in engine.ATTRIBUTES:
            workflows.create_claim(
                self.owner,
                self.org.pk,
                self.product.pk,
                {
                    "attribute": a,
                    "basis": "reported",
                    "value": "1" if a == "mass" else "10",
                    "unit": "kg" if a == "mass" else "mm",
                    "evidence_id": str(self.evidence.pk),
                    "observed_at": timezone.now(),
                },
                packaging_id=self.pack.pk,
            )
        self.equipment = services.create_equipment(self.owner, self.org.pk, definition())
        self.rules = services.create_rules(
            self.owner, self.org.pk, self.equipment.pk, self.rule_data()
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.root = f"/api/v1/organizations/{self.org.pk}/"
        self.eqpath = self.root + f"equipment/{self.equipment.pk}/"

    def rule_data(self, **changes):
        self.equipment.refresh_from_db()
        latest = self.equipment.rule_sets.first()
        return {
            "expected_equipment_version": self.equipment.version,
            "expected_rule_version": latest.number if latest else 0,
            "name": "Documented carton envelope",
            "reason": "Initial or revised documented limits",
            "evidence_policy": "reported_or_measured",
            "rules": [
                rule(a, "2" if a == "mass" else "100", "kg" if a == "mass" else "mm")
                for a in engine.ATTRIBUTES
            ],
            **changes,
        }

    def activate(self, rules=None):
        self.equipment.refresh_from_db()
        return services.activate(
            self.owner,
            self.org.pk,
            self.equipment.pk,
            (rules or self.rules).pk,
            {
                "expected_equipment_version": self.equipment.version,
                "reason": "Reviewed fixture documentation and applicability",
            },
        )

    def assessment_data(self, **changes):
        return {
            "request_id": str(uuid.uuid4()),
            "product_id": str(self.product.pk),
            "packaging_id": str(self.pack.pk),
            "equipment_id": str(self.equipment.pk),
            "rule_set_id": str(self.rules.pk),
            "orientation": "as_recorded",
            **changes,
        }


class DomainTests(Fixture, TestCase):
    def setUp(self):
        self.setup_fixture()

    def test_equipment_uniqueness_edit_versions_and_lifecycle_history(self):
        with self.assertRaises(catalog.Conflict):
            services.create_equipment(self.owner, self.org.pk, definition())
        services.create_equipment(self.outsider, self.other.pk, definition())
        updated = services.edit_equipment(
            self.owner,
            self.org.pk,
            self.equipment.pk,
            {
                "expected_version": 1,
                "reason": "New manufacturer context",
                "name": "Revised conveyor",
            },
        )
        self.assertEqual(updated.revision, 2)
        self.assertEqual(updated.revisions.last().definition["name"], "Documented conveyor")
        with self.assertRaises(catalog.Conflict):
            services.edit_equipment(
                self.owner,
                self.org.pk,
                self.equipment.pk,
                {"expected_version": 1, "reason": "Stale edit", "name": "Lost"},
            )
        archived = services.equipment_state(
            self.owner,
            self.org.pk,
            self.equipment.pk,
            {"expected_version": 2, "status": "archived", "reason": "Archive fixture"},
        )
        self.assertEqual(archived.status, "archived")
        self.assertEqual(archived.revisions.count(), 3)

    def test_rule_input_rejects_units_precision_unknown_operands_and_code(self):
        invalid = [
            rule(unit="kg"),
            rule(limit="NaN"),
            rule(limit="Infinity"),
            rule(limit="0"),
            rule(limit="-1"),
            rule(limit="0.0000001"),
            rule(margin="100"),
            rule(expression="1+1"),
            rule(type="python"),
            rule(unit=""),
            rule(allowed=["case"]),
        ]
        for data in invalid:
            with self.subTest(data=data):
                self.assertFalse(RuleInput(data=data).is_valid())
        self.assertFalse(
            AssessmentInput(
                data=self.assessment_data(organization_id=str(self.other.pk))
            ).is_valid()
        )

    def test_drafts_cannot_evaluate_activation_requires_context_and_provenance(self):
        with self.assertRaises(ValidationError):
            services.assess(self.owner, self.org.pk, self.assessment_data())
        missing = self.rule_data(rules=[rule(source_reference="")])
        draft = services.create_rules(self.owner, self.org.pk, self.equipment.pk, missing)
        with self.assertRaises(ValidationError):
            self.activate(draft)
        self.activate()
        self.assertEqual(
            services.assess(self.owner, self.org.pk, self.assessment_data()).overall, "compatible"
        )

    def test_all_roles_read_but_only_managers_edit_and_activate(self):
        for fn in [
            lambda: services.create_equipment(self.member, self.org.pk, definition("NO")),
            lambda: services.edit_equipment(self.member, self.org.pk, self.equipment.pk, {}),
            lambda: services.create_rules(self.member, self.org.pk, self.equipment.pk, {}),
            lambda: services.activate(
                self.member, self.org.pk, self.equipment.pk, self.rules.pk, {}
            ),
            lambda: services.equipment_state(self.member, self.org.pk, self.equipment.pk, {}),
        ]:
            with self.assertRaises(PermissionDenied):
                fn()
        self.activate()
        result = services.assess(self.member, self.org.pk, self.assessment_data())
        self.assertEqual(result.created_by, self.member)

    def test_immutable_rule_ids_versions_and_prior_activation(self):
        first = self.activate()
        rows = self.rule_data()
        rows["rules"][0]["id"] = first.rules[0]["id"]
        rows["rules"][0]["limit"] = "99"
        second = services.create_rules(self.owner, self.org.pk, self.equipment.pk, rows)
        self.assertEqual(second.number, 2)
        self.assertEqual(second.rules[0]["id"], first.rules[0]["id"])
        self.assertEqual(second.rules[0]["created_at"], first.rules[0]["created_at"])
        self.assertEqual(first.rules[0]["limit"], "100.000000")
        with self.assertRaises(ValueError):
            first.save()
        self.assertEqual(
            self.client.patch(
                self.eqpath + f"rule-sets/{first.pk}/", {}, format="json"
            ).status_code,
            405,
        )

    def test_source_scope_denies_foreign_evidence_and_import_ids(self):
        otherproduct = catalog.create_product(
            self.outsider,
            self.other.pk,
            {"sku": "OTHER", "revision": {"name": "Other", "change_reason": "Initial"}},
        )
        source = catalog.create_evidence(
            self.outsider,
            self.other.pk,
            otherproduct.pk,
            {
                "title": "Private",
                "source_type": "manual",
                "source_reference": "Private source",
                "attribution": "Other",
                "license": "Unknown",
                "observed_at": timezone.now(),
            },
        )
        for kind, pk in [("evidence", source.pk), ("import", uuid.uuid4())]:
            values = self.rule_data(rules=[rule(source={"kind": kind, "id": str(pk)})])
            with self.assertRaises(NotFound):
                services.create_rules(self.owner, self.org.pk, self.equipment.pk, values)
        valid = services.create_rules(
            self.owner,
            self.org.pk,
            self.equipment.pk,
            self.rule_data(rules=[rule(source={"kind": "evidence", "id": str(self.evidence.pk)})]),
        )
        self.assertEqual(valid.rules[0]["source"]["snapshot"]["title"], "Supplier record")

    def test_snapshot_survives_product_package_equipment_and_rule_changes(self):
        self.activate()
        first = services.assess(self.owner, self.org.pk, self.assessment_data())
        snapshot = copy.deepcopy(first.inputs)
        results = copy.deepcopy(first.results)
        rules = copy.deepcopy(first.rule_snapshot)
        workflows.edit_product(
            self.owner,
            self.org.pk,
            self.product.pk,
            {
                "expected_revision": 1,
                "name": "Updated product",
                "change_reason": "New catalog description",
            },
        )
        workflows.edit_configuration(
            self.owner,
            self.org.pk,
            self.product.pk,
            self.pack.pk,
            {
                "expected_version": 1,
                "name": "Updated case",
                "change_reason": "New packaging description",
            },
        )
        self.equipment.refresh_from_db()
        services.edit_equipment(
            self.owner,
            self.org.pk,
            self.equipment.pk,
            {
                "expected_version": self.equipment.version,
                "reason": "New installation context",
                "operational_context": "Revised setup",
            },
        )
        with self.assertRaises(ValidationError):
            services.assess(self.owner, self.org.pk, self.assessment_data())
        latest = services.create_rules(self.owner, self.org.pk, self.equipment.pk, self.rule_data())
        self.activate(latest)
        second = services.assess(
            self.owner,
            self.org.pk,
            self.assessment_data(rule_set_id=str(latest.pk), parent_id=str(first.pk)),
        )
        first.refresh_from_db()
        self.assertEqual(
            (first.inputs, first.results, first.rule_snapshot), (snapshot, results, rules)
        )
        self.assertNotEqual(first.product_revision_id, second.product_revision_id)
        self.assertEqual(second.parent_id, first.pk)
        self.assertEqual(first.inputs["packaging"]["name"], "Shipping case")
        self.assertTrue(services.compare(self.org, first.pk, second.pk)["changes"])

    def test_assessment_idempotency_and_request_reuse_conflict(self):
        self.activate()
        values = self.assessment_data()
        first = services.assess(self.owner, self.org.pk, values)
        before = AuditEvent.objects.count()
        self.assertEqual(services.assess(self.owner, self.org.pk, values).pk, first.pk)
        self.assertEqual(AuditEvent.objects.count(), before)
        with self.assertRaises(catalog.Conflict):
            services.assess(self.owner, self.org.pk, {**values, "orientation": "swap_length_width"})
        for path in [self.root + f"assessments/{first.pk}/"]:
            self.assertEqual(
                self.client.patch(path, {"overall": "compatible"}, format="json").status_code, 405
            )
            self.assertEqual(self.client.delete(path).status_code, 405)
        with self.assertRaises(ValueError):
            first.delete()

    def test_audit_failure_rolls_back_assessment_and_equipment(self):
        self.activate()
        with patch("compatibility.services.event", side_effect=RuntimeError("audit down")):
            with self.assertRaises(RuntimeError):
                services.assess(self.owner, self.org.pk, self.assessment_data())
            with self.assertRaises(RuntimeError):
                services.create_equipment(self.owner, self.org.pk, definition("ROLLBACK"))
        self.assertFalse(Assessment.objects.exists())
        self.assertFalse(Equipment.objects.filter(code="ROLLBACK").exists())

    def test_all_routes_anonymous_and_nested_tenant_denial(self):
        self.activate()
        assessment = services.assess(self.owner, self.org.pk, self.assessment_data())
        paths = [
            "equipment/",
            f"equipment/{self.equipment.pk}/",
            f"equipment/{self.equipment.pk}/revisions/",
            f"equipment/{self.equipment.pk}/rule-sets/",
            f"equipment/{self.equipment.pk}/rule-sets/{self.rules.pk}/",
            "assessments/",
            f"assessments/{assessment.pk}/",
            f"assessments/{assessment.pk}/compare/?other_id={assessment.pk}",
        ]
        for actor, status in [(None, 403), (self.outsider, 404)]:
            self.client.force_authenticate(actor)
            for path in paths:
                with self.subTest(path=path, status=status):
                    self.assertEqual(self.client.get(self.root + path).status_code, status)
        self.client.force_authenticate(self.outsider)
        foreignroot = f"/api/v1/organizations/{self.other.pk}/"
        self.assertEqual(
            self.client.get(foreignroot + f"assessments/{assessment.pk}/").status_code, 404
        )
        self.assertEqual(
            self.client.get(foreignroot + f"equipment/{self.equipment.pk}/").status_code, 404
        )
        self.assertEqual(
            self.client.post(
                self.root + "assessments/", self.assessment_data(), format="json"
            ).status_code,
            404,
        )

    def test_cross_tenant_product_package_rules_and_parent_references_are_scoped(self):
        self.activate()
        foreign = catalog.create_product(
            self.outsider,
            self.other.pk,
            {"sku": "FOREIGN", "revision": {"name": "Private", "change_reason": "Initial"}},
        )
        for change in [
            {"product_id": str(foreign.pk)},
            {"packaging_id": str(uuid.uuid4())},
            {"equipment_id": str(uuid.uuid4())},
            {"rule_set_id": str(uuid.uuid4())},
            {"parent_id": str(uuid.uuid4())},
        ]:
            with self.subTest(change=change), self.assertRaises(NotFound):
                services.assess(self.owner, self.org.pk, self.assessment_data(**change))
        other = services.create_equipment(self.owner, self.org.pk, definition("SECOND"))
        other_rules = services.create_rules(
            self.owner,
            self.org.pk,
            other.pk,
            {**self.rule_data(), "expected_equipment_version": 1, "expected_rule_version": 0},
        )
        with self.assertRaises(NotFound):
            services.assess(
                self.owner, self.org.pk, self.assessment_data(rule_set_id=str(other_rules.pk))
            )

    def test_archive_revocation_suspension_and_staff_do_not_bypass_scope(self):
        self.activate()
        first = services.assess(self.owner, self.org.pk, self.assessment_data())
        self.equipment.refresh_from_db()
        services.equipment_state(
            self.owner,
            self.org.pk,
            self.equipment.pk,
            {
                "expected_version": self.equipment.version,
                "status": "archived",
                "reason": "No longer available",
            },
        )
        with self.assertRaises(ValidationError):
            services.assess(self.owner, self.org.pk, self.assessment_data())
        self.assertEqual(services.assessment_get(self.org, first.pk), first)
        Membership.objects.filter(organization=self.org, user=self.member).delete()
        self.member.is_staff = True
        self.member.save()
        with self.assertRaises(NotFound):
            services.assess(self.member, self.org.pk, self.assessment_data())
        self.org.is_active = False
        self.org.save()
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(self.root + f"assessments/{first.pk}/").status_code, 404)

    def test_read_lists_filters_and_history_are_bounded_and_not_n_plus_one(self):
        self.activate()
        for _ in range(3):
            services.assess(self.owner, self.org.pk, self.assessment_data())
        result = self.client.get(
            self.root + "equipment/?search=conveyor&status=active&category=conveyor"
        )
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["count"], 1)
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(
                self.root
                + f"assessments/?product_id={self.product.pk}"
                + f"&equipment_id={self.equipment.pk}&overall=compatible"
            )
        self.assertEqual(response.json()["count"], 3)
        self.assertLessEqual(len(captured), 5)
        self.assertNotIn("inputs", response.json()["results"][0])
        for query in ["date_from=invalid", "overall=safe", "page=0", "unexpected=1"]:
            self.assertEqual(self.client.get(self.root + "assessments/?" + query).status_code, 400)

    def test_authorized_api_profile_rule_activation_and_assessment_round_trip(self):
        created = self.client.post(self.root + "equipment/", definition("API-01"), format="json")
        self.assertEqual(created.status_code, 201, created.content)
        equipment = created.json()
        path = self.root + f"equipment/{equipment['id']}/"
        changed = self.client.patch(
            path,
            {"expected_version": 1, "reason": "API edit reason", "name": "API conveyor"},
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        rules = self.client.post(
            path + "rule-sets/",
            {**self.rule_data(), "expected_equipment_version": 2, "expected_rule_version": 0},
            format="json",
        )
        self.assertEqual(rules.status_code, 201, rules.content)
        activation = self.client.post(
            path + f"rule-sets/{rules.json()['id']}/activate/",
            {"expected_equipment_version": 2, "reason": "Review all API fixture limits"},
            format="json",
        )
        self.assertEqual(activation.status_code, 200, activation.content)
        assessed = self.client.post(
            self.root + "assessments/",
            self.assessment_data(equipment_id=equipment["id"], rule_set_id=rules.json()["id"]),
            format="json",
        )
        self.assertEqual(assessed.status_code, 201, assessed.content)
        self.assertEqual(assessed.json()["overall"], "compatible")
        self.assertEqual(self.client.get(path + "revisions/").json()["count"], 2)
        self.assertEqual(
            self.client.get(path + f"rule-sets/{rules.json()['id']}/").status_code, 200
        )
        self.assertEqual(
            self.client.get(
                self.root
                + f"assessments/{assessed.json()['id']}/compare/?other_id={assessed.json()['id']}"
            ).json()["changes"],
            [],
        )

    def test_every_mutation_denies_anonymous_member_and_foreign_organization(self):
        requests = [
            ("post", "equipment/", definition("DENIED")),
            (
                "patch",
                f"equipment/{self.equipment.pk}/",
                {"expected_version": 1, "reason": "Denied modification", "name": "Denied"},
            ),
            (
                "post",
                f"equipment/{self.equipment.pk}/state/",
                {"expected_version": 1, "status": "archived", "reason": "Denied archive"},
            ),
            ("post", f"equipment/{self.equipment.pk}/rule-sets/", self.rule_data()),
            (
                "post",
                f"equipment/{self.equipment.pk}/rule-sets/{self.rules.pk}/activate/",
                {"expected_equipment_version": 1, "reason": "Denied activation reason"},
            ),
        ]
        for actor, expected_status in [(None, 403), (self.member, 403), (self.outsider, 404)]:
            self.client.force_authenticate(actor)
            for method, path, data in requests:
                with self.subTest(path=path, actor=actor):
                    self.assertEqual(
                        getattr(self.client, method)(
                            self.root + path, data, format="json"
                        ).status_code,
                        expected_status,
                    )

    def test_csrf_on_equipment_and_assessment_mutations(self):
        self.activate()
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(
            client.post(self.root + "equipment/", definition("CSRF"), format="json").status_code,
            403,
        )
        self.assertEqual(
            client.post(
                self.root + "assessments/", self.assessment_data(), format="json"
            ).status_code,
            403,
        )
        token = client.get("/api/v1/auth/csrf/").json()["csrfToken"]
        self.assertEqual(
            client.post(
                self.root + "assessments/",
                self.assessment_data(),
                format="json",
                HTTP_X_CSRFTOKEN=token,
            ).status_code,
            201,
        )

    def test_physically_attested_only_policy_uses_existing_verification_records(self):
        strict = services.create_rules(
            self.owner,
            self.org.pk,
            self.equipment.pk,
            self.rule_data(evidence_policy="measured_only"),
        )
        self.activate(strict)
        self.assertEqual(
            services.assess(
                self.owner, self.org.pk, self.assessment_data(rule_set_id=str(strict.pk))
            ).overall,
            "indeterminate",
        )
        physical = catalog.create_evidence(
            self.owner,
            self.org.pk,
            self.product.pk,
            {
                "title": "Physical test record",
                "source_type": "physical_test",
                "source_reference": "Fixture caliper and scale procedure",
                "attribution": "Test technician",
                "license": "Internal test",
                "observed_at": timezone.now(),
            },
        )
        for original in list(
            AttributeClaim.objects.filter(product=self.product, packaging=self.pack)
        ):
            workflows.verify_claim(
                self.owner,
                self.org.pk,
                self.product.pk,
                original.pk,
                {
                    "value": str(original.value),
                    "unit": original.unit,
                    "observed_at": timezone.now(),
                    "evidence_id": str(physical.pk),
                    "instrument": "Calibrated fixture instrument",
                    "procedure": "Repeated dimensional or mass observations",
                    "notes": "Synthetic test attestation, no real hardware validation",
                },
                packaging_id=self.pack.pk,
            )
        result = services.assess(
            self.owner, self.org.pk, self.assessment_data(rule_set_id=str(strict.pk))
        )
        self.assertEqual(result.overall, "compatible")
        self.assertTrue(
            all(len(state["claims"]) == 2 for state in result.inputs["attributes"].values())
        )

    def test_active_partial_specification_does_not_treat_missing_capacity_as_unlimited(self):
        partial = services.create_rules(
            self.owner,
            self.org.pk,
            self.equipment.pk,
            self.rule_data(rules=[rule("mass", "2", "kg")]),
        )
        self.activate(partial)
        result = services.assess(
            self.owner, self.org.pk, self.assessment_data(rule_set_id=str(partial.pk))
        )
        self.assertEqual(result.overall, "indeterminate")
        self.assertEqual(sum(r["type"] == "specification_coverage" for r in result.results), 3)

    def test_postgres_reference_guard_rejects_cross_tenant_assessment_reassignment(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL scope triggers required")
        self.activate()
        result = services.assess(self.owner, self.org.pk, self.assessment_data())
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE compatibility_assessment SET organization_id=%s WHERE id=%s",
                [self.other.pk, result.pk],
            )
            cursor.execute("SET CONSTRAINTS ppi_assessment_scope IMMEDIATE")

    def test_explicit_ai_specification_source_cannot_be_activated_as_documented_fact(self):
        source = catalog.create_evidence(
            self.owner,
            self.org.pk,
            self.product.pk,
            {
                "title": "Model estimate",
                "source_type": "ai_estimate",
                "source_reference": "Synthetic model",
                "attribution": "Test model",
                "license": "Unknown",
                "observed_at": timezone.now(),
            },
        )
        draft = services.create_rules(
            self.owner,
            self.org.pk,
            self.equipment.pk,
            self.rule_data(rules=[rule(source={"kind": "evidence", "id": str(source.pk)})]),
        )
        with self.assertRaises(ValidationError):
            self.activate(draft)


class ConcurrentAssessmentTests(Fixture, TransactionTestCase):
    def setUp(self):
        self.setup_fixture()

    def test_concurrent_idempotent_requests_create_one_result(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row locks required")
        self.activate()
        values = self.assessment_data()
        gate = Barrier(2)

        def run():
            close_old_connections()
            try:
                gate.wait(timeout=15)
                return services.assess(self.owner, self.org.pk, values).pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(Assessment.objects.count(), 1)
