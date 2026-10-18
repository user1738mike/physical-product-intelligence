import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from commercial.models import Assignment
from commercial.services import current
from compatibility.models import (
    Assessment,
    Equipment,
    EquipmentRevision,
    RuleActivation,
    RuleSet,
)
from ingestion.models import ImportJob
from products.models import Product, ProductRevision

from .dashboard import overview
from .dashboard_serializers import DashboardSerializer
from .models import Membership
from .services import create_organization


class DashboardTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.owner = users.objects.create_user("dashboard-owner")
        self.admin = users.objects.create_user("dashboard-admin")
        self.member = users.objects.create_user("dashboard-member")
        self.outsider = users.objects.create_user("dashboard-outsider", is_staff=True)
        self.org = create_organization(self.owner, name="Overview lab", slug="overview-lab")
        self.other = create_organization(self.outsider, name="Foreign lab", slug="foreign-lab")
        Membership.objects.create(organization=self.org, user=self.admin, role="admin")
        self.membership = Membership.objects.create(
            organization=self.org, user=self.member, role="member"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.url = f"/api/v1/organizations/{self.org.pk}/dashboard/"

    def product(self, org=None, **changes):
        item = Product.objects.create(
            organization=org or self.org, sku=str(uuid.uuid4()), **changes
        )
        revision = ProductRevision.objects.create(
            product=item, number=1, name="Fixture carton", change_reason="Test fixture"
        )
        return item, revision

    def equipment(self, *, org=None, status="active", activated=True):
        item = Equipment.objects.create(
            organization=org or self.org, code=str(uuid.uuid4()), status=status
        )
        revision = EquipmentRevision.objects.create(
            equipment=item, number=1, definition={}, reason="Test fixture"
        )
        rules = RuleSet.objects.create(
            equipment=item,
            equipment_revision=revision,
            number=1,
            name="Fixture rules",
            rules=[],
            evidence_policy="reported_or_measured",
            reason="Test fixture",
        )
        if activated:
            RuleActivation.objects.create(rule_set=rules, reason="Test fixture")
        return item, revision, rules

    def job(self, status="uploaded", org=None):
        return ImportJob.objects.create(
            organization=org or self.org,
            display_name="Fixture.csv",
            storage_key="synthetic-dashboard-fixture",
            format="csv",
            size=1,
            sha256="a" * 64,
            status=status,
        )

    def assessments(self, count, org=None):
        org = org or self.org
        product, revision = self.product(org)
        equipment, equipment_revision, rules = self.equipment(org=org)
        for index in range(count):
            Assessment.objects.create(
                organization=org,
                product=product,
                product_revision=revision,
                equipment=equipment,
                equipment_revision=equipment_revision,
                rule_set=rules,
                request_id=uuid.uuid4(),
                request_sha256="b" * 64,
                overall=["compatible", "incompatible", "indeterminate"][index % 3],
                summary="Synthetic assessment; not physical validation.",
                inputs={},
                equipment_snapshot={},
                rule_snapshot={},
                results=[],
            )

    def test_empty_state_has_real_zeroes_all_statuses_and_private_cache_policy(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        body = response.json()
        self.assertEqual(body["scope"], "all_time")
        self.assertEqual(body["organization"]["id"], str(self.org.pk))
        self.assertEqual(body["role"], "owner")
        self.assertEqual(body["products"], {"total": 0, "active": 0, "archived": 0})
        self.assertEqual(body["imports"]["by_status"], dict.fromkeys(ImportJob.Status.values, 0))
        self.assertEqual(body["imports"]["recent"], [])
        self.assertEqual(body["assessments"]["recent"], [])
        self.assertEqual(body["equipment"]["active_with_activated_rules"], 0)

    def test_totals_exceed_list_page_size_and_recent_rows_are_bounded_and_scoped(self):
        for index in range(31):
            self.product(is_active=index < 28)
        for status in ImportJob.Status.values:
            self.job(status)
        self.assessments(7)
        self.assessments(2, self.other)
        self.job("failed", self.other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["products"], {"total": 32, "active": 29, "archived": 3})
        self.assertEqual(body["imports"]["total"], 8)
        self.assertEqual(body["imports"]["awaiting_review"], 1)
        self.assertEqual(body["imports"]["attention"], 3)
        self.assertEqual(
            [row["id"] for row in body["imports"]["recent"]],
            [
                str(pk)
                for pk in ImportJob.objects.filter(organization=self.org).values_list(
                    "pk", flat=True
                )[:5]
            ],
        )
        self.assertEqual(
            {
                key: body["assessments"][key]
                for key in ("total", "compatible", "incompatible", "indeterminate")
            },
            {"total": 7, "compatible": 3, "incompatible": 2, "indeterminate": 2},
        )
        self.assertEqual(
            [row["id"] for row in body["assessments"]["recent"]],
            [
                str(pk)
                for pk in Assessment.objects.filter(organization=self.org).values_list(
                    "pk", flat=True
                )[:5]
            ],
        )
        self.assertNotIn("inputs", body["assessments"]["recent"][0])

    def test_active_configuration_requires_rules_for_current_revision_without_double_counting(self):
        ready, revision, _ = self.equipment()
        second_rules = RuleSet.objects.create(
            equipment=ready,
            equipment_revision=revision,
            number=2,
            name="Second activated version",
            rules=[],
            evidence_policy="reported_or_measured",
            reason="Test fixture",
        )
        RuleActivation.objects.create(rule_set=second_rules, reason="Test fixture")
        stale, _, _ = self.equipment()
        EquipmentRevision.objects.create(
            equipment=stale, number=2, definition={}, reason="New specification without rules"
        )
        self.equipment(activated=False)
        self.equipment(status="draft")
        self.equipment(status="archived")
        self.equipment(org=self.other)
        self.assertEqual(
            self.client.get(self.url).json()["equipment"],
            {"total": 5, "active": 3, "draft": 1, "archived": 1, "active_with_activated_rules": 1},
        )

    def test_fixed_query_budget_does_not_grow_with_recent_records(self):
        with self.assertNumQueries(8):
            empty = DashboardSerializer(overview(self.owner, self.org.pk)).data
        self.assertEqual(empty["products"]["total"], 0)
        for _ in range(9):
            self.job()
        self.assessments(9)
        with self.assertNumQueries(8):
            body = DashboardSerializer(overview(self.owner, self.org.pk)).data
        self.assertEqual(len(body["imports"]["recent"]), 5)
        self.assertEqual(len(body["assessments"]["recent"]), 5)

    def test_owner_admin_member_receive_only_shared_business_data_and_no_mutations(self):
        self.product()
        for actor, role in ((self.owner, "owner"), (self.admin, "admin"), (self.member, "member")):
            with self.subTest(role=role):
                self.client.force_authenticate(actor)
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["role"], role)
                self.assertEqual(body["products"]["total"], 1)
                self.assertNotIn("commercial", body)
                self.assertNotIn("integrations", body)
                self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 405)

    def test_foreign_revoked_inactive_account_and_suspended_organization_are_denied(self):
        self.product()
        self.client.force_authenticate(self.outsider)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("Overview lab", response.content.decode())
        self.client.force_authenticate(self.member)
        self.membership.delete()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_authenticate(self.admin)
        self.org.is_active = False
        self.org.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_expired_or_suspended_plan_keeps_existing_business_read_policy(self):
        assignment = Assignment.objects.get(organization=self.org)
        assignment.status = "suspended"
        assignment.save(update_fields=["status"])
        self.assertEqual(self.client.get(self.url).status_code, 200)
        end = timezone.now() + timedelta(hours=1)
        assignment.ends_at = end
        assignment.save(update_fields=["ends_at"])
        with patch("commercial.services.timezone.now", return_value=end + timedelta(seconds=1)):
            self.assertIsNone(current(self.org))
            self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_anonymous_unknown_filters_and_mutations_are_not_supported(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_authenticate(self.owner)
        for query in ("?page=2", "?organization_id=" + str(self.other.pk), "?scope=last_month"):
            self.assertEqual(self.client.get(self.url + query).status_code, 400)
