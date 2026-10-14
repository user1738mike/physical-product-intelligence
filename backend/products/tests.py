from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from audit.models import AuditEvent
from organizations import services as tenants
from organizations.models import Membership

from . import services
from .models import (
    Evidence,
    Measurement,
    PackagingProfile,
    Product,
    ProductRevision,
    RevisionEvidence,
)


def revision_data(**overrides):
    return {"name": "Fixture product", "change_reason": "Initial manual record", **overrides}


def evidence_data(**overrides):
    return {
        "title": "Fixture observation",
        "source_type": "manual",
        "source_reference": "Notebook entry 17",
        "attribution": "Fixture observer",
        "license": "Internal use declared by contributor",
        "observed_at": "2026-01-01T10:00:00Z",
        **overrides,
    }


def observation(source_id, **overrides):
    return {
        "property": "mass",
        "value": "1250",
        "unit": "g",
        "method": "measured",
        "observed_at": "2026-01-01T10:00:00Z",
        "evidence_id": str(source_id),
        **overrides,
    }


class ProductAPITests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="owner")
        self.other_owner = User.objects.create_user(username="other-owner")
        self.admin = User.objects.create_user(username="admin")
        self.member = User.objects.create_user(username="member")
        self.staff = User.objects.create_user(username="staff", is_staff=True, is_superuser=True)
        self.org = tenants.create_organization(self.owner, name="A", slug="a")
        self.other_org = tenants.create_organization(self.other_owner, name="B", slug="b")
        tenants.add_member(self.owner, self.org.pk, username="admin", role="admin")
        tenants.add_member(self.owner, self.org.pk, username="member")
        self.product = services.create_product(
            self.owner, self.org.pk, {"sku": "SKU-1", "revision": revision_data()}
        )
        self.other_product = services.create_product(
            self.other_owner,
            self.other_org.pk,
            {"sku": "SKU-1", "revision": revision_data(name="Private B")},
        )
        self.source = services.create_evidence(
            self.owner, self.org.pk, self.product.pk, evidence_data()
        )
        self.other_source = services.create_evidence(
            self.other_owner,
            self.other_org.pk,
            self.other_product.pk,
            evidence_data(title="Private B evidence"),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def url(self, suffix="", *, product=None, org=None):
        product = product or self.product
        org = org or self.org
        return f"/api/v1/organizations/{org.pk}/products/{product.pk}/{suffix}"

    def collection(self, org=None):
        return f"/api/v1/organizations/{(org or self.org).pk}/products/"

    def post_revision(self, payload, expected=201):
        response = self.client.post(self.url("revisions/"), payload, format="json")
        self.assertEqual(response.status_code, expected, response.content)
        return response

    def test_create_tenant_unique_sku_initial_revision_and_paginated_reads(self):
        response = self.client.post(
            self.collection(),
            {"sku": "SKU-2", "revision": revision_data(brand="Maker")},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["latest_revision_number"], 1)
        created = Product.objects.get(pk=response.json()["id"])
        self.assertEqual(created.organization, self.org)
        self.assertEqual(created.revisions.get().created_by, self.owner)
        self.assertEqual(created.revisions.get().brand, "Maker")
        self.assertEqual(self.client.get(self.collection()).json()["count"], 2)
        self.assertEqual(self.client.get(self.url()).json()["latest_revision_number"], 1)
        before = AuditEvent.objects.filter(outcome="success").count()
        duplicate = self.client.post(
            self.collection(), {"sku": "SKU-2", "revision": revision_data()}, format="json"
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(AuditEvent.objects.filter(outcome="success").count(), before)
        self.assertEqual(created.revisions.count(), 1)
        self.assertEqual(Product.objects.filter(sku="SKU-1").count(), 2)

    def test_nested_snapshot_exact_conversion_uncertainty_and_provenance(self):
        measurements = [
            observation(self.source.pk, lower="1200", upper="1300"),
            observation(self.source.pk, property="length", value="12.345678", unit="cm"),
            observation(self.source.pk, value="0.000001"),
        ]
        response = self.post_revision(
            revision_data(
                packaging=[
                    {"level": "case", "contains_level": "unit", "quantity": 12},
                    {"level": "unit", "quantity": 1, "measurements": measurements},
                ]
            )
        ).json()
        self.assertEqual(response["number"], 2)
        self.assertEqual(response["evidence_ids"], [str(self.source.pk)])
        profiles = {profile["level"]: profile for profile in response["packaging"]}
        self.assertEqual(profiles["case"]["contains_id"], profiles["unit"]["id"])
        self.assertIsNone(profiles["unit"]["fragile"])
        self.assertIsNone(profiles["unit"]["stackable"])
        values = {item["original_value"]: item for item in profiles["unit"]["measurements"]}
        self.assertEqual(values["1250.000000"]["canonical_value"], "1.250000000")
        self.assertEqual(values["1250.000000"]["canonical_lower"], "1.200000000")
        self.assertEqual(values["1250.000000"]["canonical_upper"], "1.300000000")
        self.assertEqual(values["12.345678"]["canonical_value"], "123.456780000")
        self.assertEqual(values["0.000001"]["canonical_value"], "0.000000001")
        self.assertEqual(values["1250.000000"]["conversion_version"], "metric-v1")
        self.assertEqual(values["1250.000000"]["evidence_id"], str(self.source.pk))
        self.assertEqual(self.client.get(self.url(f"revisions/{response['id']}/")).json(), response)
        packaging_url = self.url(f"revisions/{response['id']}/packaging/")
        self.assertEqual(self.client.get(packaging_url).json()["count"], 2)
        self.assertEqual(
            self.client.get(packaging_url + profiles["unit"]["id"] + "/").status_code, 200
        )

    def test_conflicting_observations_remain_distinct_and_unknowns_are_not_zero(self):
        result = self.post_revision(
            revision_data(
                packaging=[
                    {
                        "level": "unit",
                        "quantity": 1,
                        "measurements": [
                            observation(self.source.pk),
                            observation(self.source.pk, value="1500"),
                        ],
                    }
                ]
            )
        ).json()
        self.assertEqual(len(result["packaging"][0]["measurements"]), 2)
        self.assertFalse(
            any(m["property"] == "width" for m in result["packaging"][0]["measurements"])
        )
        self.assertEqual(self.product.revisions.get(number=1).packaging.count(), 0)
        self.assertEqual(self.client.get(self.url()).json()["latest_revision_number"], 2)

    def test_invalid_hierarchy_rejects_cycles_missing_levels_counts_and_duplicates(self):
        invalid = [
            [{"level": "case", "quantity": 12, "contains_level": "unit"}],
            [{"level": "unit", "quantity": 0}],
            [{"level": "unit", "quantity": 2}],
            [{"level": "unit", "quantity": 1, "contains_level": "case"}],
            [{"level": "unit", "quantity": 1}] * 2,
            [
                {"level": "unit", "quantity": 1},
                {"level": "case", "quantity": 1, "contains_level": "case"},
            ],
            [
                {"level": "unit", "quantity": 1},
                {"level": "case", "quantity": 1, "contains_level": "pallet"},
                {"level": "pallet", "quantity": 1, "contains_level": "case"},
            ],
            [{"level": "unknown", "quantity": 1}],
        ]
        for packaging in invalid:
            with self.subTest(packaging=packaging):
                self.post_revision(revision_data(packaging=packaging), expected=400)
        self.assertEqual(self.product.revisions.count(), 1)
        self.assertFalse(PackagingProfile.objects.exists())

    def test_invalid_observations_reject_dimension_mismatch_nonfinite_and_false_precision(self):
        invalid = [
            {"unit": "cm"},
            {"property": "width", "unit": "kg"},
            {"unit": "lb"},
            {"value": "0"},
            {"value": "-1"},
            {"value": "NaN"},
            {"value": "Infinity"},
            {"value": "0.0000001"},
            {"value": "1000000000000"},
            {"lower": "1200"},
            {"lower": "1300", "upper": "1400"},
            {"lower": "0", "upper": "1300"},
            {"method": "guessed"},
            {"observed_at": "2999-01-01T00:00:00Z"},
            {"evidence_id": "not-a-uuid"},
            {"canonical_value": "1"},
            {"confidence": 1},
        ]
        for changes in invalid:
            with self.subTest(changes=changes):
                self.post_revision(
                    revision_data(
                        packaging=[
                            {
                                "level": "unit",
                                "quantity": 1,
                                "measurements": [observation(self.source.pk, **changes)],
                            }
                        ]
                    ),
                    expected=400,
                )
        self.assertFalse(Measurement.objects.exists())

    def test_evidence_is_reference_only_with_declared_not_verified_digest(self):
        response = self.client.post(
            self.url("evidence/"), evidence_data(declared_sha256="a" * 64), format="json"
        )
        self.assertEqual(response.status_code, 201)
        value = response.json()
        self.assertEqual(value["capture_status"], "reference_only")
        self.assertEqual(value["declared_sha256"], "a" * 64)
        self.assertEqual(value["recorded_by_id"], self.owner.pk)
        self.assertEqual(value["product_id"], str(self.product.pk))
        self.assertEqual(self.client.get(self.url("evidence/")).json()["count"], 2)
        self.assertEqual(self.client.get(self.url(f"evidence/{value['id']}/")).json(), value)
        for changes in (
            {"declared_sha256": "invalid"},
            {"license": ""},
            {"source_reference": ""},
            {"capture_status": "verified"},
            {"object_key": "private"},
            {"product_id": str(self.other_product.pk)},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(
                    self.client.post(
                        self.url("evidence/"), evidence_data(**changes), format="json"
                    ).status_code,
                    400,
                )

    def test_cross_tenant_all_routes_hide_records_and_never_write(self):
        other_revision = self.other_product.revisions.get()
        other_packaging = PackagingProfile.objects.create(
            revision=other_revision, level="unit", quantity=1
        )
        base = self.url(product=self.other_product, org=self.other_org)
        cases = [
            ("get", self.collection(self.other_org), None),
            (
                "post",
                self.collection(self.other_org),
                {"sku": "STOLEN", "revision": revision_data()},
            ),
            ("get", base, None),
            ("post", base + "state/", {"is_active": False}),
            ("get", base + "revisions/", None),
            ("post", base + "revisions/", revision_data()),
            ("get", base + f"revisions/{other_revision.pk}/", None),
            ("get", base + "evidence/", None),
            ("post", base + "evidence/", evidence_data()),
            ("get", base + f"evidence/{self.other_source.pk}/", None),
            ("get", base + f"revisions/{other_revision.pk}/packaging/", None),
            ("get", base + f"revisions/{other_revision.pk}/packaging/{other_packaging.pk}/", None),
        ]
        before = (
            Product.objects.count(),
            ProductRevision.objects.count(),
            Evidence.objects.count(),
            AuditEvent.objects.filter(outcome="success").count(),
        )
        for method, url, data in cases:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, data, format="json")
                self.assertEqual(response.status_code, 404, response.content)
                self.assertNotIn("Private B", response.content.decode())
                self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(
            before,
            (
                Product.objects.count(),
                ProductRevision.objects.count(),
                Evidence.objects.count(),
                AuditEvent.objects.filter(outcome="success").count(),
            ),
        )
        self.other_product.refresh_from_db()
        self.assertTrue(self.other_product.is_active)

    def test_nested_ids_and_sources_cannot_cross_product_even_within_same_tenant(self):
        sibling = services.create_product(
            self.owner, self.org.pk, {"sku": "SKU-SIBLING", "revision": revision_data()}
        )
        sibling_source = services.create_evidence(
            self.owner, self.org.pk, sibling.pk, evidence_data()
        )
        sibling_revision = sibling.revisions.get()
        for source in (self.other_source, sibling_source):
            self.post_revision(revision_data(evidence_ids=[str(source.pk)]), expected=404)
            self.post_revision(
                revision_data(
                    packaging=[
                        {"level": "unit", "quantity": 1, "measurements": [observation(source.pk)]}
                    ]
                ),
                expected=404,
            )
            self.assertEqual(self.client.get(self.url(f"evidence/{source.pk}/")).status_code, 404)
        for revision in (sibling_revision, self.other_product.revisions.get()):
            self.assertEqual(
                self.client.get(self.url(f"revisions/{revision.pk}/")).status_code, 404
            )
        self.assertEqual(self.client.get(self.url(product=self.other_product)).status_code, 404)
        self.assertEqual(self.product.revisions.count(), 1)

    def test_member_contributes_admin_archives_and_history_survives_reactivation(self):
        self.client.force_authenticate(self.member)
        self.post_revision(revision_data(name="Member contribution"))
        self.assertEqual(
            self.client.post(self.url("evidence/"), evidence_data(), format="json").status_code, 201
        )
        self.assertEqual(
            self.client.post(self.url("state/"), {"is_active": False}, format="json").status_code,
            403,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(self.url("state/"), {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_active"])
        self.post_revision(revision_data(), expected=400)
        self.assertEqual(
            self.client.post(self.url("evidence/"), evidence_data(), format="json").status_code, 400
        )
        self.assertEqual(self.client.get(self.url("revisions/")).json()["count"], 2)
        self.assertEqual(
            self.client.post(self.url("state/"), {"is_active": True}, format="json").status_code,
            200,
        )
        self.post_revision(revision_data())
        self.assertEqual(self.product.revisions.count(), 3)

    def test_revoked_suspended_inactive_anonymous_and_staff_access_denied(self):
        for actor, status in ((None, 403), (self.staff, 404)):
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get(self.collection()).status_code, status)
            self.assertEqual(
                self.client.post(
                    self.collection(), {"sku": "X", "revision": revision_data()}, format="json"
                ).status_code,
                status,
            )
        self.client.force_authenticate(self.member)
        tenants.remove_member(
            self.owner,
            self.org.pk,
            Membership.objects.get(user=self.member, organization=self.org).pk,
        )
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.post_revision(revision_data(), expected=404)
        tenants.set_active(self.owner, self.org.pk, is_active=False)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(self.collection()).status_code, 404)
        self.post_revision(revision_data(), expected=404)
        tenants.set_active(self.owner, self.org.pk, is_active=True)
        self.owner.is_active = False
        self.owner.save()
        self.assertEqual(self.client.get(self.collection()).status_code, 403)

    def test_privilege_tenant_and_snapshot_fields_are_strictly_rejected(self):
        for field in ("organization_id", "id", "is_active", "created_by", "number"):
            response = self.client.post(
                self.collection(),
                {"sku": "INJECT", "revision": revision_data(), field: str(self.other_org.pk)},
                format="json",
            )
            self.assertEqual(response.status_code, 400)
        for changes in (
            {"number": 77},
            {"product_id": str(self.other_product.pk)},
            {"created_by_id": self.other_owner.pk},
            {"evidence_ids": [str(self.source.pk)] * 2},
        ):
            self.post_revision(revision_data(**changes), expected=400)
        for payload in ([], None, "text"):
            self.assertEqual(
                self.client.post(self.collection(), payload, format="json").status_code, 400
            )
        self.assertFalse(Product.objects.filter(sku="INJECT").exists())

    def test_history_is_immutable_through_api_and_orm(self):
        data = self.post_revision(
            revision_data(
                evidence_ids=[str(self.source.pk)],
                packaging=[
                    {"level": "unit", "quantity": 1, "measurements": [observation(self.source.pk)]}
                ],
            )
        ).json()
        revision = self.product.revisions.get(number=2)
        objects = [
            self.source,
            revision,
            revision.sources.get(),
            revision.packaging.get(),
            Measurement.objects.get(),
        ]
        for obj in objects:
            with self.subTest(model=type(obj).__name__):
                with self.assertRaises(ValueError):
                    obj.save()
                with self.assertRaises(ValueError):
                    obj.delete()
                with self.assertRaises(ValueError):
                    type(obj).objects.filter(pk=obj.pk).update(id=obj.pk)
                with self.assertRaises(ValueError):
                    type(obj).objects.filter(pk=obj.pk).delete()
        urls = [
            self.url(),
            self.url(f"revisions/{revision.pk}/"),
            self.url(f"evidence/{self.source.pk}/"),
            self.url(f"revisions/{revision.pk}/packaging/{data['packaging'][0]['id']}/"),
        ]
        for url in urls:
            self.assertEqual(
                self.client.patch(url, {"name": "Edited"}, format="json").status_code, 405
            )
            self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertEqual(self.client.get(self.url(f"revisions/{revision.pk}/")).json(), data)

    def test_invalid_reference_and_audit_failure_roll_back_entire_snapshot(self):
        before = (
            ProductRevision.objects.count(),
            PackagingProfile.objects.count(),
            Measurement.objects.count(),
            RevisionEvidence.objects.count(),
            AuditEvent.objects.filter(outcome="success").count(),
        )
        self.post_revision(revision_data(evidence_ids=[str(self.other_source.pk)]), expected=404)
        response = self.client.post(
            self.collection(),
            {
                "sku": "INVALID-INITIAL",
                "revision": revision_data(evidence_ids=[str(self.other_source.pk)]),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Product.objects.filter(sku="INVALID-INITIAL").exists())
        with patch("products.services.record", side_effect=RuntimeError("fixture failure")):
            with self.assertRaises(RuntimeError):
                services.create_revision(
                    self.owner,
                    self.org.pk,
                    self.product.pk,
                    revision_data(
                        packaging=[
                            {
                                "level": "unit",
                                "quantity": 1,
                                "measurements": [observation(self.source.pk)],
                            }
                        ]
                    ),
                )
            with self.assertRaises(RuntimeError):
                services.create_product(
                    self.owner, self.org.pk, {"sku": "ROLLBACK", "revision": revision_data()}
                )
        self.assertFalse(Product.objects.filter(sku="ROLLBACK").exists())
        self.assertEqual(
            before,
            (
                ProductRevision.objects.count(),
                PackagingProfile.objects.count(),
                Measurement.objects.count(),
                RevisionEvidence.objects.count(),
                AuditEvent.objects.filter(outcome="success").count(),
            ),
        )

    def test_database_constraints_reject_duplicate_revisions_and_invalid_measurements(self):
        original = self.product.revisions.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductRevision.objects.create(
                product=self.product, number=original.number, name="Bad", change_reason="Bad"
            )
        unit = PackagingProfile.objects.create(revision=original, level="unit", quantity=1)
        for changes in (
            {"original_value": Decimal("0")},
            {"canonical_unit": "mm"},
            {"original_lower": Decimal("1")},
            {"canonical_lower": Decimal("1"), "canonical_upper": Decimal("2")},
        ):
            values = {
                "packaging": unit,
                "property": "mass",
                "original_value": Decimal("1250"),
                "original_unit": "g",
                "canonical_value": Decimal("1.25"),
                "canonical_unit": "kg",
                "method": "measured",
                "observed_at": self.source.observed_at,
                "evidence": self.source,
                **changes,
            }
            with (
                self.subTest(changes=changes),
                self.assertRaises(IntegrityError),
                transaction.atomic(),
            ):
                Measurement.objects.create(**values)

    def test_pagination_is_scoped_and_stable(self):
        for number in range(26):
            services.create_product(
                self.owner, self.org.pk, {"sku": f"PAGE-{number:02}", "revision": revision_data()}
            )
        first = self.client.get(self.collection()).json()
        second = self.client.get(self.collection() + "?page=2").json()
        self.assertEqual(first["count"], 27)
        self.assertEqual(len(first["results"]), 25)
        self.assertEqual(len(second["results"]), 2)
        self.assertFalse(
            {item["id"] for item in first["results"]} & {item["id"] for item in second["results"]}
        )
        self.assertNotIn(str(self.other_product.pk), str(first) + str(second))

    def test_real_session_product_mutations_require_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        response = client.post(self.url("revisions/"), revision_data(), format="json")
        self.assertEqual(response.status_code, 403)
        token = client.get("/api/v1/auth/csrf/").json()["csrfToken"]
        response = client.post(
            self.url("revisions/"), revision_data(), format="json", HTTP_X_CSRFTOKEN=token
        )
        self.assertEqual(response.status_code, 201)

    def test_packaging_identifiers_stay_with_their_product_and_revision(self):
        first_revision = self.product.revisions.get()
        old_profile = PackagingProfile.objects.create(
            revision=first_revision, level="unit", quantity=1
        )
        new_revision = self.post_revision(
            revision_data(packaging=[{"level": "unit", "quantity": 1}])
        ).json()
        other_profile = PackagingProfile.objects.create(
            revision=self.other_product.revisions.get(), level="unit", quantity=1
        )
        for profile in (old_profile, other_profile):
            self.assertEqual(
                self.client.get(
                    self.url(f"revisions/{new_revision['id']}/packaging/{profile.pk}/")
                ).status_code,
                404,
            )

    def test_evidence_and_authorship_survive_actor_deletion_without_content_in_audit(self):
        self.client.force_authenticate(self.member)
        source = services.create_evidence(
            self.member,
            self.org.pk,
            self.product.pk,
            evidence_data(source_reference="private-content-fixture"),
        )
        revision = services.create_revision(
            self.member, self.org.pk, self.product.pk, revision_data(evidence_ids=[str(source.pk)])
        )
        self.assertNotIn(
            "private-content-fixture",
            str(list(AuditEvent.objects.filter(organization=self.org).values())),
        )
        tenants.remove_member(
            self.owner,
            self.org.pk,
            Membership.objects.get(organization=self.org, user=self.member).pk,
        )
        self.member.delete()
        source.refresh_from_db()
        revision.refresh_from_db()
        self.assertIsNone(source.recorded_by_id)
        self.assertIsNone(revision.created_by_id)
        self.assertTrue(revision.sources.filter(evidence=source).exists())


class ConcurrentRevisionTests(TransactionTestCase):
    def test_concurrent_creates_serialize_numbering_and_keep_both_snapshots(self):
        if connections["default"].vendor != "postgresql":
            self.skipTest("PostgreSQL row locks required")
        owner = get_user_model().objects.create_user(username="concurrent-owner")
        org = tenants.create_organization(owner, name="Concurrent", slug="concurrent")
        product = services.create_product(
            owner, org.pk, {"sku": "CONCURRENT", "revision": revision_data()}
        )
        barrier = Barrier(2)

        def append(index):
            try:
                actor = get_user_model().objects.get(pk=owner.pk)
                barrier.wait(timeout=20)
                return services.create_revision(
                    actor, org.pk, product.pk, revision_data(name=f"Revision {index}")
                ).number
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            numbers = list(pool.map(append, [1, 2]))
        self.assertEqual(sorted(numbers), [2, 3])
        self.assertEqual(
            list(product.revisions.order_by("number").values_list("number", flat=True)), [1, 2, 3]
        )
        self.assertEqual(
            AuditEvent.objects.filter(organization=org, action="product.revision_created").count(),
            3,
        )
