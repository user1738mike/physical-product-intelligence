from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from audit.models import AuditEvent
from audit.services import record

from . import services
from .models import Membership, Organization


class TenantTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="alice")
        self.bob = User.objects.create_user(username="bob")
        self.admin = User.objects.create_user(username="admin-a")
        self.member = User.objects.create_user(username="member-a")
        self.outsider = User.objects.create_user(username="newmember")
        self.a = services.create_organization(self.alice, name="Organization A", slug="org-a")
        self.b = services.create_organization(self.bob, name="Organization B", slug="org-b")
        self.administration = services.add_member(
            self.alice, self.a.pk, username=self.admin.username, role="admin"
        )
        self.ordinary = services.add_member(self.alice, self.a.pk, username=self.member.username)
        self.a_owner = Membership.objects.get(organization=self.a, user=self.alice)
        self.b_owner = Membership.objects.get(organization=self.b, user=self.bob)
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def url(self, org=None, suffix=""):
        return f"/api/v1/organizations/{(org or self.a).pk}/{suffix}"

    def test_initial_owner_is_caller_and_slug_retry_is_atomic(self):
        payload = {"name": "Created", "slug": "created"}
        for field in ("owner", "owner_id", "user_id", "organization_id", "is_active"):
            response = self.client.post(
                "/api/v1/organizations/", {**payload, field: self.bob.pk}, format="json"
            )
            self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/v1/organizations/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        created = Organization.objects.get(slug="created")
        self.assertEqual(Membership.objects.get(organization=created).user_id, self.alice.pk)
        self.assertEqual(Membership.objects.get(organization=created).role, "owner")
        before = AuditEvent.objects.count()
        self.assertEqual(
            self.client.post("/api/v1/organizations/", payload, format="json").status_code, 409
        )
        self.assertEqual(Membership.objects.filter(organization=created).count(), 1)
        self.assertEqual(AuditEvent.objects.count(), before)

    def test_cross_tenant_lists_detail_writes_and_memberships_are_denied(self):
        cases = [
            ("get", self.url(self.b), None),
            ("patch", self.url(self.b), {"name": "Stolen"}),
            ("get", self.url(self.b, "members/"), None),
            ("post", self.url(self.b, "members/"), {"username": "newmember"}),
            ("get", self.url(self.b, f"members/{self.b_owner.pk}/"), None),
            ("patch", self.url(self.b, f"members/{self.b_owner.pk}/"), {"role": "admin"}),
            ("delete", self.url(self.b, f"members/{self.b_owner.pk}/"), None),
            ("post", self.url(self.b, "state/"), {"is_active": False}),
            ("post", self.url(self.b, "transfer/"), {"membership_id": str(self.a_owner.pk)}),
            ("get", self.url(self.b, "audit/"), None),
        ]
        before_members = list(
            Membership.objects.filter(organization=self.b).values_list("id", "role", "user_id")
        )
        before_success = AuditEvent.objects.filter(organization=self.b, outcome="success").count()
        for method, url, data in cases:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, data, format="json")
                self.assertEqual(response.status_code, 404)
                self.assertNotIn("Organization B", response.content.decode())
        self.b.refresh_from_db()
        self.assertEqual(self.b.name, "Organization B")
        self.assertTrue(self.b.is_active)
        self.assertEqual(
            list(
                Membership.objects.filter(organization=self.b).values_list("id", "role", "user_id")
            ),
            before_members,
        )
        self.assertEqual(
            AuditEvent.objects.filter(organization=self.b, outcome="success").count(),
            before_success,
        )
        self.assertEqual(
            AuditEvent.objects.filter(action="authorization.denied", actor=self.alice).count(),
            len(cases),
        )
        self.assertEqual(self.client.delete(self.url(self.b)).status_code, 405)
        self.assertTrue(Organization.objects.filter(pk=self.b.pk).exists())

    def test_cross_tenant_nested_identifiers_never_escape_scope(self):
        for method, payload in (("get", None), ("patch", {"role": "member"}), ("delete", None)):
            response = getattr(self.client, method)(
                self.url(suffix=f"members/{self.b_owner.pk}/"), payload, format="json"
            )
            self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.client.post(
                self.url(suffix="transfer/"), {"membership_id": str(self.b_owner.pk)}, format="json"
            ).status_code,
            404,
        )
        self.b_owner.refresh_from_db()
        self.assertEqual(self.b_owner.role, "owner")

    def test_payload_cannot_move_resources_or_set_slugs_roles_or_owner(self):
        for field, value in (
            ("organization_id", str(self.b.pk)),
            ("slug", self.b.slug),
            ("owner_id", self.bob.pk),
            ("id", str(self.b.pk)),
        ):
            response = self.client.patch(self.url(), {"name": "Moved", field: value}, format="json")
            self.assertEqual(response.status_code, 400)
            response = self.client.patch(
                self.url(suffix=f"members/{self.ordinary.pk}/"),
                {"role": "admin", field: value},
                format="json",
            )
            self.assertEqual(response.status_code, 400)
            response = self.client.post(
                self.url(suffix="members/"), {"username": "newmember", field: value}, format="json"
            )
            self.assertEqual(response.status_code, 400)
        self.a.refresh_from_db()
        self.ordinary.refresh_from_db()
        self.assertEqual(self.a.name, "Organization A")
        self.assertEqual(self.ordinary.role, "member")
        self.assertEqual(self.ordinary.organization_id, self.a.pk)

    def test_member_permissions_and_no_self_escalation(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        self.assertEqual(self.client.get(self.url(suffix="members/")).status_code, 200)
        self.assertEqual(
            self.client.patch(self.url(), {"name": "Changed"}, format="json").status_code, 403
        )
        self.assertEqual(
            self.client.patch(
                self.url(suffix=f"members/{self.ordinary.pk}/"), {"role": "admin"}, format="json"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                self.url(suffix="members/"), {"username": "newmember"}, format="json"
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get(self.url(suffix="audit/")).status_code, 403)
        self.ordinary.refresh_from_db()
        self.assertEqual(self.ordinary.role, "member")

    def test_admin_can_manage_members_but_never_privileges(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.patch(self.url(), {"name": "Renamed"}, format="json").status_code, 200
        )
        self.assertEqual(
            self.client.post(
                self.url(suffix="members/"),
                {"username": "newmember", "role": "admin"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(
                self.url(suffix=f"members/{self.administration.pk}/"),
                {"role": "member"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(self.url(suffix=f"members/{self.administration.pk}/")).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                self.url(suffix="state/"), {"is_active": False}, format="json"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                self.url(suffix="transfer/"),
                {"membership_id": str(self.administration.pk)},
                format="json",
            ).status_code,
            403,
        )
        added = self.client.post(
            self.url(suffix="members/"), {"username": "newmember"}, format="json"
        )
        self.assertEqual(added.status_code, 201)
        self.assertEqual(
            self.client.delete(self.url(suffix=f"members/{added.json()['id']}/")).status_code, 204
        )
        self.assertFalse(
            Membership.objects.filter(organization=self.a, user=self.outsider).exists()
        )
        self.assertEqual(self.client.get(self.url(suffix="audit/")).status_code, 200)

    def test_owner_changes_roles_duplicates_rejected_and_single_owner_constraints(self):
        response = self.client.patch(
            self.url(suffix=f"members/{self.ordinary.pk}/"), {"role": "admin"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.ordinary.refresh_from_db()
        self.assertEqual(self.ordinary.role, "admin")
        duplicate = self.client.post(
            self.url(suffix="members/"), {"username": self.member.username}, format="json"
        )
        self.assertEqual(duplicate.status_code, 400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(organization=self.a, user=self.member)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(organization=self.a, user=self.outsider, role="owner")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(organization=self.a, user=self.outsider, role="invented")

    def test_last_owner_and_transactional_transfer(self):
        self.assertEqual(
            self.client.delete(self.url(suffix=f"members/{self.a_owner.pk}/")).status_code, 400
        )
        self.assertEqual(
            self.client.patch(
                self.url(suffix=f"members/{self.a_owner.pk}/"), {"role": "member"}, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                self.url(suffix="members/"),
                {"username": "newmember", "role": "owner"},
                format="json",
            ).status_code,
            400,
        )
        response = self.client.post(
            self.url(suffix="transfer/"), {"membership_id": str(self.ordinary.pk)}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.a_owner.refresh_from_db()
        self.ordinary.refresh_from_db()
        self.assertEqual(self.a_owner.role, "admin")
        self.assertEqual(self.ordinary.role, "owner")
        self.assertEqual(Membership.objects.filter(organization=self.a, role="owner").count(), 1)
        self.assertEqual(
            self.client.post(
                self.url(suffix="state/"), {"is_active": False}, format="json"
            ).status_code,
            403,
        )

    def test_suspension_revocation_and_inactive_target(self):
        self.outsider.is_active = False
        self.outsider.save()
        self.assertEqual(
            self.client.post(
                self.url(suffix="members/"), {"username": self.outsider.username}, format="json"
            ).status_code,
            404,
        )
        services.remove_member(self.alice, self.a.pk, self.ordinary.pk)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.client.force_authenticate(self.alice)
        self.assertEqual(
            self.client.post(
                self.url(suffix="state/"), {"is_active": False}, format="json"
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.assertEqual(self.client.get(self.url(suffix="members/")).status_code, 404)
        self.assertEqual(
            self.client.patch(self.url(), {"name": "Blocked"}, format="json").status_code, 404
        )
        own = self.client.get("/api/v1/auth/memberships/").json()
        self.assertFalse(own["results"][0]["organization"]["is_active"])
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.post(
                self.url(suffix="state/"), {"is_active": True}, format="json"
            ).status_code,
            403,
        )
        self.client.force_authenticate(self.alice)
        self.assertEqual(
            self.client.post(
                self.url(suffix="state/"), {"is_active": True}, format="json"
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get(self.url()).status_code, 200)

    def test_staff_has_no_implicit_tenant_access_and_lists_are_scoped_paginated(self):
        self.alice.is_staff = self.alice.is_superuser = True
        self.alice.save()
        self.assertEqual(self.client.get(self.url(self.b)).status_code, 404)
        data = self.client.get("/api/v1/auth/memberships/").json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["organization"]["id"], str(self.a.pk))
        for index in range(26):
            user = get_user_model().objects.create_user(username=f"person-{index}")
            Membership.objects.create(organization=self.a, user=user)
        data = self.client.get(self.url(suffix="members/")).json()
        self.assertEqual(len(data["results"]), 25)
        self.assertIsNotNone(data["next"])
        self.assertNotIn(self.bob.pk, [item["user"]["id"] for item in data["results"]])

    def test_success_audit_rollback_retention_and_no_mutation_api(self):
        before = AuditEvent.objects.count()
        with patch("organizations.services.record", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                services.rename_organization(self.alice, self.a.pk, name="Must roll back")
        self.a.refresh_from_db()
        self.assertEqual(self.a.name, "Organization A")
        self.assertEqual(AuditEvent.objects.count(), before)
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                services.create_organization(self.alice, name="Rolled back", slug="rolled-back")
                raise RuntimeError("force rollback")
        self.assertFalse(Organization.objects.filter(slug="rolled-back").exists())
        self.assertEqual(AuditEvent.objects.count(), before)
        with self.assertRaises(ValueError):
            record("invalid", metadata={"password": "never-store"})
        events = self.client.get(self.url(suffix="audit/")).json()["results"]
        self.assertTrue(any(event["action"] == "organization.created" for event in events))
        for event in events:
            self.assertLessEqual(set(event["metadata"]), {"role", "previous_role"})
        event = AuditEvent.objects.filter(organization=self.a).first()
        with self.assertRaises(ValueError):
            event.save()
        with self.assertRaises(ValueError):
            event.delete()
        with self.assertRaises(ValueError):
            AuditEvent.objects.filter(pk=event.pk).update(action="changed")
        for method in ("post", "patch", "delete"):
            self.assertEqual(
                getattr(self.client, method)(
                    self.url(suffix="audit/"), {}, format="json"
                ).status_code,
                405,
            )
        with self.assertRaises(ProtectedError):
            self.a.delete()
        self.assertTrue(AuditEvent.objects.filter(pk=event.pk).exists())

    def test_failed_transfer_rolls_back_both_roles_and_success_events(self):
        before = AuditEvent.objects.count()
        with patch("organizations.services.record", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                services.transfer_ownership(self.alice, self.a.pk, membership_id=self.ordinary.pk)
        self.a_owner.refresh_from_db()
        self.ordinary.refresh_from_db()
        self.assertEqual(self.a_owner.role, "owner")
        self.assertEqual(self.ordinary.role, "member")
        self.assertEqual(AuditEvent.objects.count(), before)

    def test_actor_deletion_preserves_audit_without_personal_identity(self):
        actor = get_user_model().objects.create_user(username="disposable-actor")
        event = record("account.created", actor=actor)
        actor.delete()
        event.refresh_from_db()
        self.assertIsNone(event.actor_id)
        self.assertEqual(event.action, "account.created")


class OwnershipConcurrencyTests(TransactionTestCase):
    def test_concurrent_transfers_serialize_and_leave_exactly_one_owner(self):
        if connection.vendor != "postgresql":
            self.skipTest("Requires PostgreSQL row locks")
        User = get_user_model()
        owner = User.objects.create_user(username="owner")
        organization = services.create_organization(owner, name="Concurrency", slug="concurrency")
        targets = [
            Membership.objects.create(
                organization=organization, user=User.objects.create_user(username=f"target-{index}")
            )
            for index in range(2)
        ]
        barrier = Barrier(2)

        def transfer(target):
            close_old_connections()
            try:
                actor = User.objects.get(pk=owner.pk)
                barrier.wait(timeout=10)
                try:
                    services.transfer_ownership(actor, organization.pk, membership_id=target.pk)
                    return "success"
                except PermissionDenied:
                    return "denied"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(transfer, targets))
        self.assertCountEqual(results, ["success", "denied"])
        self.assertEqual(
            Membership.objects.filter(organization=organization, role="owner").count(), 1
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                organization=organization, action="ownership.transferred"
            ).count(),
            1,
        )
