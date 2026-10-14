from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from audit.models import AuditEvent
from organizations import services as tenants
from organizations.models import Membership

from . import services, workflows
from .models import (
    AttributeClaim,
    ClaimSelection,
    ClaimVerification,
    PackagingConfiguration,
)
from .tests import evidence_data, revision_data


class CatalogWorkflowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="workflow-owner")
        self.admin = User.objects.create_user(username="workflow-admin")
        self.member = User.objects.create_user(username="workflow-member")
        self.other = User.objects.create_user(username="workflow-other")
        self.org = tenants.create_organization(self.owner, name="Workflow", slug="workflow")
        self.other_org = tenants.create_organization(
            self.other, name="Other", slug="workflow-other"
        )
        tenants.add_member(self.owner, self.org.pk, username=self.admin.username, role="admin")
        tenants.add_member(self.owner, self.org.pk, username=self.member.username)
        self.product = services.create_product(
            self.owner, self.org.pk, {"sku": "WF-01", "revision": revision_data()}
        )
        self.other_product = services.create_product(
            self.other,
            self.other_org.pk,
            {"sku": "WF-01", "revision": revision_data(name="Secret other catalog")},
        )
        self.pack = workflows.create_configuration(
            self.owner, self.org.pk, self.product.pk, {"name": "Retail unit", "level": "unit"}
        )
        self.other_pack = workflows.create_configuration(
            self.other,
            self.other_org.pk,
            self.other_product.pk,
            {"name": "Other unit", "level": "unit"},
        )
        self.source = services.create_evidence(
            self.owner, self.org.pk, self.product.pk, evidence_data()
        )
        self.physical = services.create_evidence(
            self.owner, self.org.pk, self.product.pk, evidence_data(source_type="physical_test")
        )
        self.other_source = services.create_evidence(
            self.other, self.other_org.pk, self.other_product.pk, evidence_data()
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.base = f"/api/v1/organizations/{self.org.pk}/products/{self.product.pk}/"
        self.other_base = (
            f"/api/v1/organizations/{self.other_org.pk}/products/{self.other_product.pk}/"
        )

    def claim_data(self, **changes):
        return {
            "attribute": "mass",
            "basis": "reported",
            "value": "1200",
            "unit": "g",
            "evidence_id": str(self.source.pk),
            "observed_at": "2026-01-01T10:00:00Z",
            **changes,
        }

    def add_claim(self, *, base=None, **changes):
        response = self.client.post(
            (base or self.base) + "claims/", self.claim_data(**changes), format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def verification_data(self, **changes):
        return {
            "value": "1.35",
            "unit": "kg",
            "evidence_id": str(self.physical.pk),
            "observed_at": "2026-01-01T12:00:00Z",
            "instrument": "Calibrated scale, fixture 17",
            "procedure": "Zero the scale and weigh one sealed unit.",
            "notes": "One unit measured; sampling remains limited.",
            **changes,
        }

    def state(self, base=None, attribute="mass"):
        result = self.client.get((base or self.base) + "attributes/")
        self.assertEqual(result.status_code, 200, result.content)
        return next(row for row in result.json()["results"] if row["attribute"] == attribute)

    def test_product_patch_appends_snapshot_and_rejects_stale_updates(self):
        response = self.client.patch(
            self.base,
            {"name": "Updated fixture", "expected_revision": 1, "change_reason": "Correct name"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["latest_revision_number"], 2)
        self.assertEqual(response.json()["name"], "Updated fixture")
        self.assertEqual(self.product.revisions.get(number=1).name, "Fixture product")
        self.assertEqual(
            self.client.patch(
                self.base,
                {"name": "Lost update", "expected_revision": 1, "change_reason": "Stale"},
                format="json",
            ).status_code,
            409,
        )
        self.assertEqual(self.product.revisions.count(), 2)
        for field in ("sku", "organization_id", "is_active", "created_by_id"):
            self.assertEqual(
                self.client.patch(
                    self.base,
                    {"expected_revision": 2, "change_reason": "Injection", field: "bad"},
                    format="json",
                ).status_code,
                400,
            )

    def test_catalog_search_order_filters_and_validation(self):
        collection = f"/api/v1/organizations/{self.org.pk}/products/"
        self.assertEqual(self.client.get(collection + "?search=WF-01").json()["count"], 1)
        self.assertEqual(
            self.client.get(collection + "?search=fixture&ordering=-name").json()["count"], 1
        )
        self.assertEqual(self.client.get(collection + "?search=Secret").json()["count"], 0)
        for query in (
            "ordering=organization_id",
            "search=" + "x" * 101,
            "status=deleted",
            "page=0",
            "page=100001",
            "unsafe=1",
        ):
            self.assertEqual(self.client.get(collection + "?" + query).status_code, 400)
        services.set_product_active(self.owner, self.org.pk, self.product.pk, {"is_active": False})
        self.assertEqual(self.client.get(collection + "?status=active").json()["count"], 0)
        self.assertEqual(self.client.get(collection + "?status=archived").json()["count"], 1)

    def test_packaging_create_edit_archival_history_and_versions(self):
        url = self.base + f"packaging/{self.pack.pk}/"
        self.assertEqual(self.client.get(self.base + "packaging/").json()["count"], 1)
        response = self.client.patch(
            url,
            {
                "material": "Cardboard",
                "quantity": 12,
                "expected_version": 1,
                "change_reason": "Record material and count",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["version"], 2)
        self.assertEqual(
            self.client.patch(
                url,
                {"name": "Stale", "expected_version": 1, "change_reason": "No overwrite"},
                format="json",
            ).status_code,
            409,
        )
        history = self.client.get(url + "revisions/").json()["results"]
        self.assertEqual([row["version"] for row in history], [2, 1])
        self.assertIsNone(history[1]["quantity"])
        self.assertEqual(history[0]["change_reason"], "Record material and count")
        self.client.force_authenticate(self.member)
        self.assertEqual(
            self.client.post(
                url + "state/", {"is_active": False, "expected_version": 2}, format="json"
            ).status_code,
            403,
        )
        self.client.force_authenticate(self.admin)
        archived = self.client.post(
            url + "state/", {"is_active": False, "expected_version": 2}, format="json"
        )
        self.assertEqual(archived.status_code, 200)
        self.assertFalse(archived.json()["is_active"])
        self.assertEqual(
            self.client.post(url + "claims/", self.claim_data(), format="json").status_code, 400
        )
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(
            self.client.post(
                url + "state/", {"is_active": True, "expected_version": 3}, format="json"
            ).status_code,
            200,
        )

    def test_packaging_required_fields_quantities_and_ownership_are_strict(self):
        for payload in (
            {"level": "unit"},
            {"name": "Bad", "level": "unknown"},
            {"name": "Bad", "level": "case", "quantity": 0},
            {"name": "Bad", "level": "unit", "product_id": str(self.other_product.pk)},
            {"name": "Bad", "level": "unit", "organization_id": str(self.other_org.pk)},
            {"name": "Bad", "level": "unit", "is_active": False},
        ):
            self.assertEqual(
                self.client.post(self.base + "packaging/", payload, format="json").status_code, 400
            )
        self.assertEqual(
            self.client.post(
                self.base + "packaging/", {"name": "Retail unit", "level": "case"}, format="json"
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.delete(self.base + f"packaging/{self.pack.pk}/").status_code, 405
        )

    def test_unknown_reported_estimated_measured_are_distinct_and_immutable(self):
        self.assertEqual(self.state()["status"], "unknown")
        reported = self.add_claim()
        self.assertEqual(reported["basis"], "reported")
        self.assertIsNone(reported["verification_record"])
        self.assertEqual(reported["canonical_value"], "1.200000000")
        estimated = self.add_claim(
            basis="estimated",
            value="1300",
            method="Geometric estimate, method fixture v1",
            limitations="No physical sample; approximation only",
        )
        self.assertEqual(estimated["basis"], "estimated")
        self.assertEqual(self.state()["status"], "conflict")
        self.assertIsNone(self.state()["selected_claim"])
        measured = self.client.post(
            self.base + f"claims/{estimated['id']}/verification/",
            self.verification_data(),
            format="json",
        )
        self.assertEqual(measured.status_code, 201, measured.content)
        self.assertEqual(measured.json()["basis"], "measured")
        record = measured.json()["verification_record"]
        self.assertEqual(record["verified_by_id"], self.owner.pk)
        self.assertEqual(record["claim_id"], estimated["id"])
        self.assertTrue(record["verified_at"])
        original = self.client.get(self.base + f"claims/{estimated['id']}/").json()
        self.assertEqual(original["basis"], "estimated")
        self.assertEqual(len(original["verifications"]), 1)
        self.assertEqual(
            self.client.patch(
                self.base + f"claims/{estimated['id']}/", {"basis": "measured"}, format="json"
            ).status_code,
            405,
        )

    def test_verification_requires_role_physical_source_and_details(self):
        claim = self.add_claim()
        url = self.base + f"claims/{claim['id']}/verification/"
        self.client.force_authenticate(self.member)
        self.assertEqual(
            self.client.post(url, self.verification_data(), format="json").status_code, 403
        )
        self.assertEqual(
            self.client.post(
                self.base + "claims/", self.claim_data(basis="measured"), format="json"
            ).status_code,
            400,
        )
        self.client.force_authenticate(self.admin)
        for change in (
            {"evidence_id": str(self.source.pk)},
            {"procedure": ""},
            {"instrument": ""},
            {"verified_by_id": self.member.pk},
            {"unit": "cm"},
            {"value": "0"},
            {"notes": ""},
        ):
            self.assertEqual(
                self.client.post(url, self.verification_data(**change), format="json").status_code,
                400,
            )
        self.assertFalse(ClaimVerification.objects.exists())
        self.assertEqual(
            self.client.post(url, self.verification_data(), format="json").status_code, 201
        )

    def test_claim_validation_units_ranges_precision_and_estimation_method(self):
        invalid = [
            {"unit": ""},
            {"unit": "lb"},
            {"unit": "cm"},
            {"value": "-1"},
            {"value": "0"},
            {"value": "NaN"},
            {"value": "0.0000001"},
            {"lower": "1000"},
            {"lower": "1300", "upper": "1500"},
            {"basis": "estimated"},
            {"confidence": 0.99},
            {"verified_at": "2026-01-01T00:00:00Z"},
            {"attribute": "unsafe_formula"},
            {"attribute": "brand", "value": None, "unit": "", "text_value": ""},
        ]
        for changes in invalid:
            with self.subTest(changes=changes):
                self.assertEqual(
                    self.client.post(
                        self.base + "claims/", self.claim_data(**changes), format="json"
                    ).status_code,
                    400,
                )
        self.assertFalse(AttributeClaim.objects.exists())
        text = self.add_claim(attribute="brand", value=None, unit="", text_value="Reported brand")
        self.assertIsNone(text["canonical_value"])
        tiny = self.add_claim(value="0.000001")
        self.assertEqual(tiny["canonical_value"], "0.000000001")

    def test_ai_source_cannot_be_relabelled_reported_or_verified(self):
        source = services.create_evidence(
            self.member, self.org.pk, self.product.pk, evidence_data(source_type="ai_estimate")
        )
        self.assertEqual(
            self.client.post(
                self.base + "claims/", self.claim_data(evidence_id=str(source.pk)), format="json"
            ).status_code,
            400,
        )
        claim = self.add_claim(
            evidence_id=str(source.pk),
            basis="estimated",
            method="Declared external model v1",
            limitations="Not physically validated",
        )
        self.assertEqual(
            self.client.post(
                self.base + f"claims/{claim['id']}/verification/",
                self.verification_data(evidence_id=str(source.pk)),
                format="json",
            ).status_code,
            400,
        )

    def test_conflict_selection_is_authorized_retained_and_new_conflicts_invalidate_selection(self):
        first = self.add_claim()
        second = self.add_claim(value="1350")
        url = self.base + "attributes/mass/selection/"
        payload = {
            "claim_id": second["id"],
            "rationale": "Prefer the later documented source for this review.",
        }
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 403)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 201)
        state = self.state()
        self.assertEqual(state["status"], "resolved")
        self.assertEqual(state["selected_claim"]["id"], second["id"])
        self.assertEqual(AttributeClaim.objects.count(), 2)
        self.add_claim(value="1350")
        self.assertEqual(self.state()["status"], "resolved")
        self.assertEqual(self.state()["selected_claim"]["id"], second["id"])
        self.add_claim(value="1400")
        self.assertEqual(self.state()["status"], "conflict")
        self.assertIsNone(self.state()["selected_claim"])
        self.assertEqual(ClaimSelection.objects.count(), 1)
        self.assertEqual(
            self.client.post(
                self.base + "attributes/width/selection/",
                {**payload, "claim_id": first["id"]},
                format="json",
            ).status_code,
            400,
        )

    def test_packaging_claims_have_correct_scope_and_product_scope_stays_unknown(self):
        base = self.base + f"packaging/{self.pack.pk}/"
        claim = self.add_claim(base=base)
        sources = self.client.get(base + "evidence/")
        self.assertEqual(sources.status_code, 200)
        self.assertEqual(sources.json()["count"], 1)
        self.assertEqual(sources.json()["results"][0]["id"], str(self.source.pk))
        self.assertEqual(claim["packaging_id"], str(self.pack.pk))
        self.assertEqual(self.state(base)["status"], "reported")
        self.assertEqual(self.state()["status"], "unknown")
        self.assertEqual(self.client.get(self.base + f"claims/{claim['id']}/").status_code, 404)

    def test_all_new_routes_deny_cross_tenant_and_nested_product_ids(self):
        other_claim = workflows.create_claim(
            self.other,
            self.other_org.pk,
            self.other_product.pk,
            self.claim_data(evidence_id=str(self.other_source.pk)),
            packaging_id=self.other_pack.pk,
        )
        base = self.other_base
        packing = base + f"packaging/{self.other_pack.pk}/"
        for method, url, payload in [
            ("patch", base, {"name": "Stolen", "expected_revision": 1, "change_reason": "Invalid"}),
            ("get", base + "packaging/", None),
            ("post", base + "packaging/", {"name": "Stolen", "level": "unit"}),
            ("get", packing, None),
            (
                "patch",
                packing,
                {"name": "Stolen", "expected_version": 1, "change_reason": "Invalid"},
            ),
            ("post", packing + "state/", {"is_active": False, "expected_version": 1}),
            ("get", packing + "revisions/", None),
            ("get", packing + "evidence/", None),
            ("get", base + "history/", None),
            ("get", packing + "history/", None),
            ("get", packing + "claims/", None),
            ("post", packing + "claims/", self.claim_data()),
            ("get", packing + f"claims/{other_claim.pk}/", None),
            ("post", packing + f"claims/{other_claim.pk}/verification/", self.verification_data()),
            ("get", packing + "attributes/", None),
            (
                "post",
                packing + "attributes/mass/selection/",
                {"claim_id": str(other_claim.pk), "rationale": "Stolen scope reference"},
            ),
        ]:
            with self.subTest(method=method, url=url):
                result = getattr(self.client, method)(url, payload, format="json")
                self.assertEqual(result.status_code, 404, result.content)
                self.assertNotIn("Secret other", result.content.decode())
        nested = self.base + f"packaging/{self.other_pack.pk}/"
        self.assertEqual(self.client.get(nested).status_code, 404)
        self.assertEqual(
            self.client.post(
                self.base + "claims/",
                self.claim_data(evidence_id=str(self.other_source.pk)),
                format="json",
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                self.base + "attributes/mass/selection/",
                {"claim_id": str(other_claim.pk), "rationale": "Wrong product source selection"},
                format="json",
            ).status_code,
            404,
        )
        self.assertFalse(ClaimVerification.objects.exists())

    def test_member_reads_scoped_history_without_global_audit_access(self):
        self.add_claim()
        self.client.force_authenticate(self.member)
        result = self.client.get(self.base + "history/")
        self.assertEqual(result.status_code, 200, result.content)
        rows = result.json()["results"]
        self.assertTrue(any(row["action"] == "evidence.claim_reported" for row in rows))
        self.assertTrue(all(row["actor_id"] == self.owner.pk for row in rows))
        self.assertTrue(all(row["timestamp"] for row in rows))
        self.assertNotIn("Notebook entry", str(rows))
        self.assertEqual(
            self.client.get(f"/api/v1/organizations/{self.org.pk}/audit/").status_code, 403
        )
        self.assertEqual(
            self.client.patch(self.base + "history/", {}, format="json").status_code, 405
        )

    def test_archive_revocation_suspension_and_anonymous_apply_to_new_workflows(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.base + "packaging/").status_code, 403)
        self.client.force_authenticate(self.member)
        tenants.remove_member(
            self.owner,
            self.org.pk,
            Membership.objects.get(organization=self.org, user=self.member).pk,
        )
        self.assertEqual(
            self.client.post(self.base + "claims/", self.claim_data(), format="json").status_code,
            404,
        )
        self.client.force_authenticate(self.owner)
        services.set_product_active(self.owner, self.org.pk, self.product.pk, {"is_active": False})
        self.assertEqual(
            self.client.post(self.base + "claims/", self.claim_data(), format="json").status_code,
            400,
        )
        self.assertEqual(self.client.get(self.base + "history/").status_code, 200)
        tenants.set_active(self.owner, self.org.pk, is_active=False)
        self.assertEqual(self.client.get(self.base + "attributes/").status_code, 404)

    def test_audit_failure_rolls_back_claim_verification_selection_and_packaging(self):
        claim = self.add_claim()
        before = AuditEvent.objects.filter(outcome="success").count()
        with patch("products.services.record", side_effect=RuntimeError("Fixture audit failure")):
            for operation in [
                lambda: workflows.create_configuration(
                    self.owner, self.org.pk, self.product.pk, {"name": "Rollback", "level": "case"}
                ),
                lambda: workflows.verify_claim(
                    self.owner, self.org.pk, self.product.pk, claim["id"], self.verification_data()
                ),
                lambda: workflows.select_claim(
                    self.owner,
                    self.org.pk,
                    self.product.pk,
                    "mass",
                    {"claim_id": claim["id"], "rationale": "Selection must roll back with audit"},
                ),
            ]:
                with self.assertRaises(RuntimeError):
                    operation()
        self.assertEqual(AttributeClaim.objects.count(), 1)
        self.assertFalse(ClaimVerification.objects.exists())
        self.assertFalse(ClaimSelection.objects.exists())
        self.assertFalse(PackagingConfiguration.objects.filter(name="Rollback").exists())
        self.assertEqual(AuditEvent.objects.filter(outcome="success").count(), before)

    def test_claims_and_history_are_immutable_and_database_constraints_reject_bad_units(self):
        claim = workflows.create_claim(self.owner, self.org.pk, self.product.pk, self.claim_data())
        for obj in [claim, self.pack.revisions.get()]:
            with self.assertRaises(ValueError):
                obj.save()
            with self.assertRaises(ValueError):
                type(obj).objects.filter(pk=obj.pk).delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttributeClaim.objects.create(
                product=self.product,
                attribute="mass",
                basis="reported",
                value=1,
                unit="cm",
                canonical_value=1,
                canonical_unit="mm",
                evidence=self.source,
                observed_at=self.source.observed_at,
            )
        for field in ("value", "canonical_value"):
            with (
                self.subTest(field=field),
                self.assertRaises(IntegrityError),
                transaction.atomic(),
            ):
                # Bypass DecimalField's own NaN rejection to exercise the SQL guard.
                with connection.cursor() as cursor:
                    cursor.execute(
                        f'UPDATE products_attributeclaim SET "{field}" = %s WHERE id = %s',
                        [Decimal("NaN"), claim.pk],
                    )

    def test_nested_source_and_claim_are_atomic_and_foreign_sources_stay_scoped(self):
        payload = self.claim_data()
        payload.pop("evidence_id")
        payload["source"] = evidence_data(source_type="manufacturer_spec")
        response = self.client.post(self.base + "claims/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["evidence"]["source_type"], "manufacturer_spec")
        before = self.product.evidence.count()
        bad = {**payload, "source": evidence_data(source_type="ai_estimate")}
        self.assertEqual(
            self.client.post(self.base + "claims/", bad, format="json").status_code, 400
        )
        self.assertEqual(self.product.evidence.count(), before)
        invalid_verification = self.verification_data()
        invalid_verification.pop("evidence_id")
        invalid_verification["source"] = evidence_data(source_type="physical_test")
        measured = self.client.post(
            self.base + f"claims/{response.json()['id']}/verification/",
            invalid_verification,
            format="json",
        )
        self.assertEqual(measured.status_code, 201, measured.content)
        self.assertEqual(measured.json()["basis"], "measured")

    def test_regular_member_can_create_and_edit_packaging_but_not_reassign_it(self):
        self.client.force_authenticate(self.member)
        result = self.client.post(
            self.base + "packaging/",
            {"name": "Member case", "level": "case", "quantity": 6},
            format="json",
        )
        self.assertEqual(result.status_code, 201)
        url = self.base + f"packaging/{result.json()['id']}/"
        result = self.client.patch(
            url,
            {
                "expected_version": 1,
                "change_reason": "Record case material",
                "material": "Cardboard",
            },
            format="json",
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(
            self.client.patch(
                url,
                {
                    "expected_version": 2,
                    "change_reason": "Reassign",
                    "product_id": str(self.other_product.pk),
                },
                format="json",
            ).status_code,
            400,
        )

    def test_postgres_guards_reject_cross_resource_orm_writes_and_unbacked_verification(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL constraint triggers required")
        for changes in (
            {"evidence": self.other_source},
            {"packaging": self.other_pack},
            {"basis": "measured"},
        ):
            with (
                self.subTest(changes=changes),
                self.assertRaises(IntegrityError),
                transaction.atomic(),
            ):
                with connection.cursor() as cursor:
                    cursor.execute("SET CONSTRAINTS ppi_scope_claim IMMEDIATE")
                values = {
                    "product": self.product,
                    "evidence": self.source,
                    "attribute": "mass",
                    "basis": "reported",
                    "value": 1,
                    "unit": "kg",
                    "canonical_value": 1,
                    "canonical_unit": "kg",
                    "observed_at": self.source.observed_at,
                    **changes,
                }
                AttributeClaim.objects.create(**values)


class ConcurrentCatalogEditTests(TransactionTestCase):
    def test_one_of_two_stale_product_edits_is_rejected_without_losing_history(self):
        if connections["default"].vendor != "postgresql":
            self.skipTest("Requires PostgreSQL row locks")
        owner = get_user_model().objects.create_user(username="optimistic-owner")
        org = tenants.create_organization(owner, name="Optimistic", slug="optimistic")
        product = services.create_product(
            owner, org.pk, {"sku": "OPT", "revision": revision_data()}
        )
        barrier = Barrier(2)

        def change(number):
            try:
                actor = get_user_model().objects.get(pk=owner.pk)
                barrier.wait(timeout=20)
                try:
                    workflows.edit_product(
                        actor,
                        org.pk,
                        product.pk,
                        {
                            "expected_revision": 1,
                            "name": f"Edit {number}",
                            "change_reason": "Concurrent update",
                        },
                    )
                    return "saved"
                except workflows.StaleWrite:
                    return "stale"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(change, [1, 2])), ["saved", "stale"])
        self.assertEqual(product.revisions.count(), 2)
