"""Actual local HTTPS APIs and signed loopback receiver; no external service is contacted."""

import hashlib
import json
import secrets
import ssl
import threading
import uuid
from datetime import timedelta
from http.client import HTTPConnection
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from integrations import services, signing
from integrations.models import Delivery, Event
from integrations.rehearsal import enable_plan, require
from organizations.models import Organization


class Command(BaseCommand):
    help = "Isolated synthetic demonstration; secrets exist only in process memory."

    def add_arguments(self, parser):
        parser.add_argument("--ca", required=True)

    def handle(self, *args, **options):
        require()
        self.stage = "synthetic initialization"
        receiver, thread = None, None
        try:
            origin = "https://edge:8443"  # Fixed isolated Compose ingress; never customer-selected.
            username, password = (
                "integration-demo-" + uuid.uuid4().hex[:12],
                secrets.token_urlsafe(32),
            )
            get_user_model().objects.create_user(username, password=password)
            opener = build_opener(
                HTTPCookieProcessor(CookieJar()),
                HTTPSHandler(context=ssl.create_default_context(cafile=options["ca"])),
            )

            def call(path, data=None, bearer=None, expected=200):
                headers = {"Accept": "application/json", "Origin": origin}
                if bearer:
                    headers["Authorization"] = "Bearer " + bearer
                if data is not None:
                    csrf = call("/api/v1/auth/csrf/")
                    headers.update(
                        {"X-CSRFToken": csrf["csrfToken"], "Content-Type": "application/json"}
                    )
                request = Request(
                    origin + path,
                    data=json.dumps(data).encode() if data is not None else None,
                    headers=headers,
                )
                self.stage = path
                try:
                    response = opener.open(request, timeout=15)
                except HTTPError as error:
                    if error.code == expected:
                        error.close()
                        return None
                    raise RuntimeError("Synthetic API step failed") from None
                with response:
                    if response.status != expected:
                        raise RuntimeError("Synthetic API status mismatch")
                    body = response.read(1024 * 1024 + 1)
                    if len(body) > 1024 * 1024:
                        raise RuntimeError("Synthetic response limit exceeded")
                    return json.loads(body) if body else None

            call("/api/v1/auth/login/", {"username": username, "password": password})
            org = call(
                "/api/v1/organizations/",
                {
                    "name": "Synthetic warehouse demo",
                    "slug": "warehouse-demo-" + uuid.uuid4().hex[:12],
                },
                expected=201,
            )
            enable_plan(Organization.objects.get(pk=org["id"]))
            root = f"/api/v1/organizations/{org['id']}/"
            credential = call(
                root + "integrations/credentials/",
                {
                    "name": "Warehouse demo reader",
                    "scopes": ["catalog:read", "assessments:read", "assessments:export"],
                    "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(),
                },
                expected=201,
            )
            destination = call(
                root + "integrations/destinations/",
                {
                    "url": "https://warehouse.example/events",
                    "subscriptions": ["assessment.completed"],
                    "enabled": True,
                },
                expected=201,
            )
            token, webhook_secret = credential.pop("secret"), destination.pop("secret")
            seen, verified = set(), []

            class Receiver(BaseHTTPRequestHandler):
                def do_POST(self):
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 8192:
                        self.send_error(413)
                        return
                    body = self.rfile.read(length)
                    event_id = self.headers.get("webhook-id", "")
                    valid = signing.verify(
                        webhook_secret,
                        event_id,
                        self.headers.get("webhook-timestamp", ""),
                        body,
                        self.headers.get("webhook-signature", ""),
                    )
                    if valid:
                        verified.append(hashlib.sha256(body).hexdigest())
                        seen.add(
                            event_id
                        )  # Exactly one synthetic receiver effect per stable event ID.
                    self.send_response(204 if valid else 400)
                    self.send_header("Content-Length", "0")
                    self.end_headers()

                def log_message(self, *args):
                    pass  # No headers, bodies or secrets are logged.

            receiver = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
            receiver.daemon_threads = True
            thread = threading.Thread(target=receiver.serve_forever, daemon=True)
            thread.start()

            def local_sender(url, body, headers):
                require()
                if url != "https://warehouse.example/events":
                    raise RuntimeError("Unexpected synthetic destination")
                client = HTTPConnection("127.0.0.1", receiver.server_port, timeout=3)
                try:
                    client.request("POST", "/events", body=body, headers=headers)
                    response = client.getresponse()
                    response.read(4096)
                    return response.status, None
                finally:
                    client.close()

            product = call(
                root + "products/",
                {
                    "sku": "WAREHOUSE-DEMO",
                    "revision": {"name": "Synthetic carton", "change_reason": "Synthetic API demo"},
                },
                expected=201,
            )
            equipment = call(
                root + "equipment/",
                {
                    "code": "WAREHOUSE-DEMO",
                    "name": "Synthetic conveyor",
                    "category": "conveyor",
                    "operational_context": "Synthetic limits only",
                    "supported_levels": ["unit"],
                    "source_reference": "Synthetic fixture",
                },
                expected=201,
            )
            eq = root + f"equipment/{equipment['id']}/"
            rules = call(
                eq + "rule-sets/",
                {
                    "expected_equipment_version": equipment["version"],
                    "expected_rule_version": 0,
                    "name": "Synthetic envelope",
                    "reason": "Synthetic demo",
                    "evidence_policy": "reported_or_measured",
                    "rules": [
                        {
                            "id": str(uuid.uuid4()),
                            "type": "maximum",
                            "name": "Synthetic length",
                            "explanation": "Unknown dimensions remain indeterminate",
                            "severity": "hard",
                            "enabled": True,
                            "attribute": "length",
                            "limit": "100",
                            "unit": "mm",
                            "margin": "0",
                            "source_reference": "Synthetic fixture",
                        }
                    ],
                },
                expected=201,
            )
            equipment = call(eq)
            call(
                eq + f"rule-sets/{rules['id']}/activate/",
                {
                    "expected_equipment_version": equipment["version"],
                    "reason": "Synthetic reviewed rule",
                },
            )
            data = {
                "request_id": str(uuid.uuid4()),
                "product_id": product["id"],
                "equipment_id": equipment["id"],
                "rule_set_id": rules["id"],
                "orientation": "as_recorded",
                "product_level": "unit",
            }
            assessment = call(root + "assessments/", data, expected=201)
            duplicate = call(root + "assessments/", data, expected=201)
            if assessment["id"] != duplicate["id"]:
                raise RuntimeError("Assessment retry duplicated business work")
            catalog = call("/api/v1/integration/products/", bearer=token)
            exported = call(
                f"/api/v1/integration/assessments/{assessment['id']}/export/json/", bearer=token
            )
            delivery = Delivery.objects.get(
                event__assessment_id=assessment["id"], destination_id=destination["id"]
            )
            self.stage = "signed loopback delivery"
            if services.dispatch_one(delivery.pk, sender=local_sender) != "delivered":
                raise RuntimeError("Synthetic delivery failed")
            call(root + f"integrations/deliveries/{delivery.pk}/replay/", {}, expected=200)
            if (
                services.dispatch_one(delivery.pk, sender=local_sender) != "delivered"
                or len(verified) != 2
                or len(seen) != 1
                or len(set(verified)) != 1
            ):
                raise RuntimeError("Receiver verification or deduplication failed")
            call(root + f"integrations/credentials/{credential['id']}/revoke/", {})
            call("/api/v1/integration/products/", bearer=token, expected=401)
            if (
                exported["overall"] != "indeterminate"
                or exported["assessment_id"] != assessment["id"]
                or len(catalog["results"]) != 1
                or Event.objects.filter(assessment_id=assessment["id"]).count() != 1
            ):
                raise RuntimeError("Synthetic snapshot/identity check failed")
            self.stdout.write(
                json.dumps(
                    {
                        "status": "passed",
                        "transport": "isolated_loopback_test_only",
                        "actual_https_api": True,
                        "organization_id": org["id"],
                        "assessment_id": assessment["id"],
                        "verified_deliveries": len(verified),
                        "receiver_effects": len(seen),
                        "stable_body_sha256": verified[0],
                        "export_result": exported["overall"],
                        "credential_revocation_status": 401,
                        "live_destinations": 0,
                        "live_ai_calls": 0,
                        "real_payment_requests": 0,
                    }
                )
            )
        except Exception:
            raise CommandError(
                "Synthetic integration demonstration failed at "
                + self.stage
                + "; secret output suppressed."
            ) from None
        finally:
            if receiver:
                receiver.shutdown()
                receiver.server_close()
            if thread:
                thread.join(timeout=3)
