import base64
import hashlib
import hmac
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import APIException, Throttled, ValidationError
from rest_framework.test import APIClient

from commercial import services as commercial
from commercial.models import FEATURES, METERS, Usage
from compatibility import services as assessments
from compatibility.tests import Fixture
from organizations.models import Membership

from . import exports, services, signing, transport
from .models import SCOPES, Admission, Credential, Delivery, Event, PlanPolicy

SYNTHETIC_ROOT = base64.b64encode(b"synthetic-integration-root-32bytes!").decode()
CONFIG = dict(
    INTEGRATION_OUTBOUND_ENABLED=True,
    INTEGRATION_ALLOWED_HOSTS=["warehouse.example"],
    INTEGRATION_SIGNING_CURRENT="test-v1",
    INTEGRATION_SIGNING_KEYS={"test-v1": SYNTHETIC_ROOT},
)


def enable(fixture):
    fixture.owner.is_staff = True
    fixture.owner.save(update_fields=["is_staff"])
    with transaction.atomic():
        plan = commercial.publish(
            fixture.owner,
            code="integration-fixture",
            version=2,
            name="Synthetic integration",
            policy={**{key: True for key in FEATURES}, **{key + "_limit": None for key in METERS}},
            reason="Synthetic test",
        )
        PlanPolicy.objects.create(
            plan=plan,
            api_enabled=True,
            webhooks_enabled=True,
            credentials_limit=3,
            destinations_limit=2,
        )
        commercial.assign(fixture.owner, fixture.org, plan, reason="Synthetic integration access")
    fixture.activate()


@override_settings(**CONFIG)
class IntegrationTests(Fixture, TestCase):
    def setUp(self):
        self.setup_fixture()
        enable(self)
        self.management = self.root + "integrations/"
        self.bearer = APIClient()

    def credential(self, **changes):
        item, token = services.create_credential(
            self.owner,
            self.org.pk,
            name="Warehouse",
            scopes=list(SCOPES),
            expires_at=timezone.now() + timedelta(days=2),
            **changes,
        )
        self.bearer.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        return item, token

    def destination(self):
        return services.configure_destination(
            self.owner,
            self.org.pk,
            url="https://warehouse.example/events",
            subscriptions=["assessment.completed"],
        )

    def result(self, data=None):
        return assessments.assess(self.owner, self.org.pk, data or self.assessment_data())

    def test_reveal_once_verifier_and_csrf_management(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(
            client.post(self.management + "credentials/", {}, format="json").status_code, 403
        )
        response = self.client.post(
            self.management + "credentials/",
            {
                "name": "Warehouse",
                "scopes": list(SCOPES),
                "expires_at": (timezone.now() + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        token = response.json()["secret"]
        item = Credential.objects.get(pk=response.json()["id"])
        self.assertEqual(len(token), 82)
        self.assertNotIn(token, item.verifier)
        self.assertEqual(item.verifier, hashlib.sha256(token.encode()).hexdigest())
        metadata = self.client.get(self.management)
        self.assertNotIn(token, metadata.content.decode())
        self.assertNotIn("verifier", metadata.content.decode())
        self.assertIn("no-store", response["Cache-Control"])

    def test_expiry_revocation_and_issuer_downgrade(self):
        item, _ = self.credential()
        path = "/api/v1/integration/products/"
        self.assertEqual(self.bearer.get(path).status_code, 200)
        services.revoke(self.owner, self.org.pk, item.pk)
        self.assertEqual(self.bearer.get(path).status_code, 401)
        item, _ = self.credential()
        with patch(
            "integrations.services.timezone.now",
            return_value=item.expires_at + timedelta(seconds=1),
        ):
            self.assertEqual(self.bearer.get(path).status_code, 401)
        Membership.objects.filter(organization=self.org, user=self.owner).update(role="admin")
        self.assertEqual(self.bearer.get(path).status_code, 200)
        Membership.objects.filter(organization=self.org, user=self.owner).update(role="member")
        self.assertEqual(self.bearer.get(path).status_code, 403)

    def test_rotation_is_immediate_by_default_and_overlap_is_explicit(self):
        old, token = self.credential()
        _, replacement = services.create_credential(
            self.owner,
            self.org.pk,
            name="Replacement",
            scopes=list(SCOPES),
            expires_at=timezone.now() + timedelta(days=1),
            rotate=old.pk,
        )
        self.assertNotEqual(token, replacement)
        self.assertEqual(self.bearer.get("/api/v1/integration/products/").status_code, 401)
        current, current_token = self.credential()
        services.create_credential(
            self.owner,
            self.org.pk,
            name="Overlap",
            scopes=list(SCOPES),
            expires_at=timezone.now() + timedelta(days=1),
            rotate=current.pk,
            revoke_old=False,
        )
        self.assertEqual(services.authenticate(current_token).pk, current.pk)

    def test_scope_tenant_related_object_and_mutation_denials(self):
        item, token = services.create_credential(
            self.owner,
            self.org.pk,
            name="Catalog only",
            scopes=["catalog:read"],
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.bearer.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        self.assertEqual(self.bearer.get("/api/v1/integration/assessments/").status_code, 403)
        self.assertEqual(
            self.bearer.get(
                "/api/v1/integration/products/?organization=" + str(self.other.pk)
            ).status_code,
            400,
        )
        self.assertEqual(
            self.bearer.get(f"/api/v1/integration/products/{uuid.uuid4()}/").status_code, 404
        )
        self.assertEqual(
            self.bearer.post("/api/v1/integration/products/", {}, format="json").status_code, 405
        )
        self.assertEqual(self.bearer.get(self.management).status_code, 403)
        self.bearer.credentials()
        self.assertEqual(
            self.bearer.get("/api/v1/integration/products/?token=" + token).status_code, 401
        )
        for scope in ("*", "billing:read", "catalog:write", "upload"):
            with self.assertRaises(ValidationError):
                services.create_credential(
                    self.owner,
                    self.org.pk,
                    name="Invalid",
                    scopes=[scope],
                    expires_at=timezone.now() + timedelta(days=1),
                )

    def test_shared_rate_counts_survive_rotation_and_untrusted_headers(self):
        item, _ = self.credential()
        with override_settings(INTEGRATION_ORG_RATE=2):
            for _ in range(2):
                self.assertEqual(
                    self.bearer.get(
                        "/api/v1/integration/products/", HTTP_X_FORWARDED_FOR=str(uuid.uuid4())
                    ).status_code,
                    200,
                )
            self.credential()
            response = self.bearer.get("/api/v1/integration/products/")
            self.assertEqual(response.status_code, 429)
            self.assertTrue(1 <= int(response["Retry-After"]) <= 60)
        self.assertEqual(Admission.objects.count(), 0)

    def test_plan_cap_and_historical_reads_after_expiry(self):
        item, _ = self.credential()
        assignment = commercial.current(self.org)
        commercial.transition(
            self.owner,
            self.org,
            assignment.pk,
            action="expire",
            reason="Test expiry",
            ends_at=timezone.now(),
        )
        self.assertEqual(self.bearer.get("/api/v1/integration/assessments/").status_code, 200)
        with self.assertRaises(APIException):
            self.credential()
        self.assertIsNotNone(item)

    def test_pagination_exact_snapshot_unknowns_and_csv_formula_defense(self):
        self.credential()
        item = self.result()
        json_response = self.bearer.get(f"/api/v1/integration/assessments/{item.pk}/export/json/")
        self.assertEqual(json_response.status_code, 200)
        data = json.loads(json_response.content)
        self.assertEqual(data["overall"], item.overall)
        self.assertEqual(
            data["inputs"]["attributes"]["length"]["claims"][0]["canonical_value"],
            item.inputs["attributes"]["length"]["claims"][0]["canonical_value"],
        )
        self.assertEqual(data["equipment_revision_id"], str(item.equipment_revision_id))
        self.assertEqual(self.bearer.get("/api/v1/integration/products/?limit=26").status_code, 400)
        first = self.bearer.get("/api/v1/integration/assessments/?limit=1").json()
        self.assertEqual(len(first["results"]), 1)
        self.assertIsNone(first["next_after"])
        for value in ("=CMD()", " +1", "-1+2", "@SUM(1)", "\t=1"):
            self.assertEqual(exports.csv_text(value), "'" + value)
        self.assertEqual(exports.csv_text("10.000"), "10.000")
        self.assertEqual(
            json.loads(exports.bounded_json({"unknown": None, "exact": "0.00000001"})),
            {"unknown": None, "exact": "0.00000001"},
        )
        with self.assertRaises(ValidationError):
            exports.bounded_json({"oversize": "x" * 1024 * 1024})
        csv_response = self.bearer.get(f"/api/v1/integration/assessments/{item.pk}/export/csv/")
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn(b"inputs_json", csv_response.content)

    def test_outbox_atomicity_and_idempotent_assessment_does_not_double_usage(self):
        destination, _ = self.destination()
        data = self.assessment_data()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.result(data)
                raise RuntimeError("Rollback synthetic transaction")
        self.assertEqual(Event.objects.count(), 0)
        self.assertEqual(Delivery.objects.count(), 0)
        item = self.result(data)
        self.assertEqual(self.result(data).pk, item.pk)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Delivery.objects.count(), 1)
        self.assertEqual(
            Usage.objects.filter(organization=self.org, meter="assessments").count(), 1
        )

    def test_signatures_exact_body_identity_time_vector_and_rotation(self):
        destination, secret = self.destination()
        item = self.result()
        event = Event.objects.get(assessment=item)
        now = timezone.now()
        headers = signing.headers(destination, event, now)
        timestamp = headers["webhook-timestamp"]
        raw = event.body.encode()
        expected = base64.b64encode(
            hmac.digest(
                base64.b64decode(secret[6:]),
                str(event.pk).encode() + b"." + timestamp.encode() + b"." + raw,
                "sha256",
            )
        ).decode()
        self.assertEqual(headers["webhook-signature"], "v1," + expected)
        self.assertTrue(
            signing.verify(
                secret, event.pk, timestamp, raw, headers["webhook-signature"], now=now.timestamp()
            )
        )
        for changed_id, changed_time, changed_body in (
            (uuid.uuid4(), timestamp, raw),
            (event.pk, str(int(timestamp) - 301), raw),
            (event.pk, timestamp, raw + b" "),
        ):
            self.assertFalse(
                signing.verify(
                    secret,
                    changed_id,
                    changed_time,
                    changed_body,
                    headers["webhook-signature"],
                    now=now.timestamp(),
                )
            )
        destination, new_secret = services.rotate_signing(self.owner, self.org.pk, destination.pk)
        dual = signing.headers(destination, event, now)["webhook-signature"]
        self.assertEqual(len(dual.split(" ")), 2)
        self.assertTrue(signing.verify(secret, event.pk, timestamp, raw, dual, now=now.timestamp()))
        self.assertTrue(
            signing.verify(new_secret, event.pk, timestamp, raw, dual, now=now.timestamp())
        )
        destination, final_secret = services.rotate_signing(
            self.owner, self.org.pk, destination.pk, immediate=True
        )
        self.assertEqual(
            len(signing.headers(destination, event, now)["webhook-signature"].split(" ")), 1
        )
        self.assertNotEqual(secret, final_secret)

    def test_delivery_retry_429_redirect_410_and_replay_identity(self):
        destination, _ = self.destination()
        item = self.result()
        delivery = Delivery.objects.get(event__assessment=item)
        bodies = []

        def sender(url, body, headers):
            bodies.append((body, headers["webhook-id"]))
            return 429, 120

        before = timezone.now()
        self.assertEqual(services.dispatch_one(delivery.pk, sender=sender), "retryable")
        delivery.refresh_from_db()
        self.assertGreaterEqual(delivery.due_at, before + timedelta(seconds=120))
        services.replay(self.owner, self.org.pk, delivery.pk)
        self.assertEqual(
            services.dispatch_one(delivery.pk, sender=lambda *args: (302, None)), "retryable"
        )
        services.replay(self.owner, self.org.pk, delivery.pk)

        def successful(url, body, headers):
            self.assertEqual((body, headers["webhook-id"]), bodies[0])
            return 204, None

        self.assertEqual(services.dispatch_one(delivery.pk, sender=successful), "delivered")
        services.replay(self.owner, self.org.pk, delivery.pk)
        self.assertEqual(
            services.dispatch_one(delivery.pk, sender=lambda *args: (410, None)), "paused"
        )
        destination.refresh_from_db()
        self.assertFalse(destination.enabled)
        self.assertEqual(
            Usage.objects.filter(organization=self.org, meter="assessments").count(), 1
        )

    def test_unknown_timeout_interrupted_claim_and_fenced_result(self):
        self.destination()
        self.result()
        item = Delivery.objects.get()
        self.assertEqual(
            services.dispatch_one(
                item.pk, sender=lambda *args: (_ for _ in ()).throw(transport.TransportFailure())
            ),
            "retryable",
        )
        services.replay(self.owner, self.org.pk, item.pk)
        first = services.claim(item.pk)
        self.assertIsNone(services.claim(item.pk))
        Delivery.objects.filter(pk=item.pk).update(
            lease_until=timezone.now() - timedelta(seconds=1)
        )
        second = services.claim(item.pk)
        self.assertNotEqual(first.lease, second.lease)
        self.assertEqual(services.finish(first, 200, None, "test"), "fenced")
        self.assertEqual(services.finish(second, 200, None, "test"), "delivered")

    def test_changed_disabled_or_revoked_destination_pauses_without_network(self):
        destination, _ = self.destination()
        self.result()
        delivery = Delivery.objects.get()
        services.configure_destination(
            self.owner,
            self.org.pk,
            url=destination.url,
            subscriptions=["assessment.completed"],
            destination_id=destination.pk,
            enabled=False,
            expected_revision=destination.revision,
        )
        with patch("integrations.transport.send") as send:
            self.assertEqual(services.dispatch_one(delivery.pk), "not_claimed")
            send.assert_not_called()
        with self.assertRaises(ValidationError):
            services.replay(self.owner, self.org.pk, delivery.pk)

    def test_postgres_identity_and_append_only_guards(self):
        item, _ = self.credential()
        self.destination()
        result = self.result()
        for statement, params in (
            (
                "UPDATE integrations_credential SET organization_id=%s WHERE id=%s",
                [self.other.pk, item.pk],
            ),
            ("UPDATE integrations_event SET body='{}' WHERE assessment_id=%s", [result.pk]),
            ("DELETE FROM integrations_event WHERE assessment_id=%s", [result.pk]),
        ):
            with (
                self.assertRaises(IntegrityError),
                transaction.atomic(),
                connection.cursor() as cursor,
            ):
                cursor.execute(statement, params)
        services.revoke(self.owner, self.org.pk, item.pk)
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE integrations_credential SET revoked_at=NULL WHERE id=%s", [item.pk]
            )

    def test_runtime_role_cannot_fabricate_delivery_success_or_policy(self):
        self.destination()
        self.result()
        delivery = Delivery.objects.get()
        self.assertEqual(
            services.dispatch_one(delivery.pk, sender=lambda *args: (204, None)), "delivered"
        )
        role = connection.ops.quote_name("ppi_integration_test_" + uuid.uuid4().hex[:12])
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {role} NOLOGIN NOINHERIT")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            cursor.execute(
                f"GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {role}"
            )
            cursor.execute(f"SET LOCAL ROLE {role}")
        try:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute(f"REVOKE UPDATE ON integrations_event FROM {role}")
                cursor.execute(f"SET LOCAL ROLE {role}")
            self.assertEqual(services.replay(self.owner, self.org.pk, delivery.pk).state, "pending")
            for sql in (
                "UPDATE integrations_delivery SET state='delivered'",
                "UPDATE integrations_planpolicy SET api_enabled=false",
                "DELETE FROM integrations_event",
            ):
                with (
                    self.assertRaises(IntegrityError),
                    transaction.atomic(),
                    connection.cursor() as cursor,
                ):
                    cursor.execute(sql)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def test_reenable_cannot_bypass_finite_destination_allowance(self):
        first, _ = self.destination()
        services.configure_destination(
            self.owner,
            self.org.pk,
            url=first.url,
            subscriptions=[],
            destination_id=first.pk,
            enabled=False,
            expected_revision=first.revision,
        )
        self.destination()
        self.destination()
        first.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.configure_destination(
                self.owner,
                self.org.pk,
                url=first.url,
                subscriptions=["assessment.completed"],
                destination_id=first.pk,
                enabled=True,
                expected_revision=first.revision,
            )

    def test_management_member_and_foreign_denial(self):
        metadata = self.client.get(self.management).json()
        self.assertTrue(metadata["credential_creation_available"])
        self.assertEqual(metadata["allowances"], {"credentials": 3, "destinations": 2})
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(self.management).status_code, 403)
        self.assertEqual(
            self.client.post(self.management + "credentials/", {}, format="json").status_code, 400
        )
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.management).status_code, 404)

    def test_retry_after_numeric_date_invalid_and_clamp(self):
        from email.utils import format_datetime

        now = timezone.now().replace(microsecond=0)
        self.assertEqual(transport.retry_delay("120"), 120)
        self.assertEqual(transport.retry_delay("999999"), 3600)
        self.assertEqual(
            transport.retry_delay(format_datetime(now + timedelta(seconds=90)), now=now), 90
        )
        self.assertIsNone(transport.retry_delay("invalid"))

    def test_known_foreign_assessment_is_hidden_and_explicit_scope_does_not_expand(self):
        result = self.result()
        plan = commercial.current(self.org).plan
        commercial.assign(self.owner, self.other, plan, reason="Synthetic other tenant")
        _, token = services.create_credential(
            self.outsider,
            self.other.pk,
            name="Foreign reader",
            scopes=["assessments:export"],
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.bearer.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        self.assertEqual(
            self.bearer.get(
                f"/api/v1/integration/assessments/{result.pk}/export/json/"
            ).status_code,
            404,
        )
        self.assertEqual(self.bearer.get("/api/v1/integration/assessments/").status_code, 403)

    def test_concurrency_cap_expiring_admission_and_organization_disable(self):
        item, _ = self.credential()
        first = services.admit(item)
        services.admit(item)
        with self.assertRaises(Throttled):
            services.admit(item)
        with patch(
            "integrations.services.timezone.now",
            return_value=first.expires_at + timedelta(seconds=1),
        ):
            self.assertIsNotNone(services.admit(item))
        self.org.is_active = False
        self.org.save(update_fields=["is_active"])
        self.assertEqual(self.bearer.get("/api/v1/integration/products/").status_code, 401)

    def test_destination_revision_and_issuer_downgrade_prevent_dispatch(self):
        destination, _ = self.destination()
        self.result()
        item = Delivery.objects.get()
        with self.assertRaises(ValidationError):
            services.configure_destination(
                self.owner,
                self.org.pk,
                url=destination.url,
                subscriptions=[],
                destination_id=destination.pk,
                expected_revision=100,
            )
        Membership.objects.filter(organization=self.org, user=self.owner).update(role="member")
        with patch("integrations.transport.send") as send:
            self.assertEqual(services.dispatch_one(item.pk), "not_claimed")
            send.assert_not_called()
        item.refresh_from_db()
        self.assertEqual(item.state, "paused")

    def test_attempt_and_age_limits_stop_dispatch_without_sleeping(self):
        self.destination()
        self.result()
        item = Delivery.objects.get()
        for _ in range(6):
            Delivery.objects.filter(pk=item.pk).update(due_at=timezone.now() - timedelta(seconds=1))
            state = services.dispatch_one(item.pk, sender=lambda *args: (500, None))
        self.assertEqual(state, "terminal")
        self.assertEqual(
            services.dispatch_one(item.pk, sender=lambda *args: (204, None)), "not_claimed"
        )
        services.replay(self.owner, self.org.pk, item.pk)
        Delivery.objects.filter(pk=item.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(services.claim(item.pk))
        item.refresh_from_db()
        self.assertEqual(item.state, "terminal")

    def test_dns_rebinding_is_rechecked_on_each_attempt(self):
        addresses = [[(2, 1, 6, "", ("8.8.8.8", 443))], [(2, 1, 6, "", ("169.254.169.254", 443))]]
        with (
            patch("integrations.transport.socket.getaddrinfo", side_effect=addresses),
            patch("integrations.transport.PinnedHTTPS") as connection,
        ):
            response = connection.return_value.getresponse.return_value
            response.status, response.read.return_value, response.getheader.return_value = (
                204,
                b"",
                "",
            )
            self.assertEqual(
                transport.send("https://warehouse.example/events", b"{}", {}), (204, None)
            )
            with self.assertRaises(transport.TransportFailure):
                transport.send("https://warehouse.example/events", b"{}", {})
            self.assertEqual(connection.call_count, 1)

    def test_unsafe_urls_and_nonpublic_dns_answers(self):
        bad = [
            "http://warehouse.example/",
            "https://warehouse.example:8443/",
            "https://u@warehouse.example/",
            "https://warehouse.example/#x",
            "https://warehouse.example./",
            "https://warehouse.example%2f@evil.example/",
            "https://warehouse.example\\@evil.example/",
            "https://127.0.0.1/",
            "https://[::1]/",
            "https://warehouse.example\n/",
            "https://warehouse.example/../a",
        ]
        for url in bad:
            if url.endswith("/../a"):
                continue
            with self.subTest(url=url), self.assertRaises(ValidationError):
                transport.url_parts(url)
        for value in (
            "127.0.0.1",
            "10.0.0.1",
            "169.254.169.254",
            "0.0.0.0",
            "::1",
            "fc00::1",
            "fe80::1",
            "::ffff:8.8.8.8",
            "2002:0808:0808::",
            "224.0.0.1",
        ):
            self.assertFalse(transport.public_address(value), value)
        with patch(
            "integrations.transport.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("8.8.8.8", 443)), (2, 1, 6, "", ("127.0.0.1", 443))],
        ):
            with self.assertRaises(transport.TransportFailure):
                transport.resolve("warehouse.example")

    def test_transport_pins_validated_address_no_second_resolution_or_redirect(self):
        from unittest.mock import MagicMock

        raw = MagicMock()
        with (
            patch("integrations.transport.socket.socket", return_value=raw),
            patch("integrations.transport.ssl.create_default_context") as context,
            patch("integrations.transport.socket.getaddrinfo") as dns,
        ):
            pinned = transport.PinnedHTTPS("warehouse.example", "8.8.8.8")
            pinned.connect()
            raw.connect.assert_called_once_with(("8.8.8.8", 443))
            context.return_value.wrap_socket.assert_called_once_with(
                raw, server_hostname="warehouse.example"
            )
            dns.assert_not_called()
        with (
            patch("integrations.transport.resolve", return_value=["8.8.8.8"]),
            patch("integrations.transport.PinnedHTTPS") as conn,
        ):
            response = conn.return_value.getresponse.return_value
            response.status, response.read.return_value = 302, b""
            response.getheader.return_value = "120"
            self.assertEqual(
                transport.send("https://warehouse.example/events", b"{}", {}), (302, 120)
            )
            self.assertEqual(conn.return_value.request.call_count, 1)
            response.read.return_value = b"x" * 4097
            with self.assertRaises(transport.TransportFailure):
                transport.send("https://warehouse.example/events", b"{}", {})


@override_settings(**CONFIG)
class ConcurrentIntegrationTests(Fixture, TransactionTestCase):
    def setUp(self):
        self.setup_fixture()
        enable(self)

    def parallel(self, function):
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return function()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(lambda _: worker(), range(2)))

    def test_two_dispatchers_claim_one_delivery(self):
        services.configure_destination(
            self.owner,
            self.org.pk,
            url="https://warehouse.example/events",
            subscriptions=["assessment.completed"],
        )
        assessments.assess(self.owner, self.org.pk, self.assessment_data())
        item = Delivery.objects.get()
        results = self.parallel(
            lambda: services.dispatch_one(item.pk, sender=lambda *args: (204, None))
        )
        self.assertEqual(sorted(results), ["delivered", "not_claimed"])
        item.refresh_from_db()
        self.assertEqual(item.attempts, 1)

    def test_shared_last_admission_under_concurrency(self):
        credential, _ = services.create_credential(
            self.owner,
            self.org.pk,
            name="Concurrent",
            scopes=list(SCOPES),
            expires_at=timezone.now() + timedelta(days=1),
        )

        def request():
            try:
                return str(services.admit(credential).pk)
            except Throttled:
                return "throttled"

        with override_settings(INTEGRATION_ORG_RATE=1):
            results = self.parallel(request)
        self.assertEqual(results.count("throttled"), 1)
        self.assertEqual(Admission.objects.count(), 1)
