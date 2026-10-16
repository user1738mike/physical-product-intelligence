"""Synthetic recovery/persistence checks with real Django login+CSRF under runtime DML role."""

import hashlib
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test import Client

from operations.database import runtime_role_privileged


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--context", required=True)

    def handle(self, *args, **options):
        if not re.fullmatch(
            r"ppi_(rehearsal|restore)_[a-f0-9]{10}", connection.settings_dict["NAME"]
        ):
            raise CommandError("Synthetic access probe refuses a working database")
        if runtime_role_privileged():
            raise CommandError("Access probe requires non-owner runtime identity")
        fixture = json.loads(Path(options["context"]).read_text())
        base = f"/api/v1/organizations/{fixture['organization_id']}/"

        def login(credentials):
            browser = Client(enforce_csrf_checks=True, HTTP_HOST="localhost")
            token = browser.get("/api/v1/auth/csrf/", secure=True).json()["csrfToken"]
            response = browser.post(
                "/api/v1/auth/login/",
                credentials,
                content_type="application/json",
                secure=True,
                HTTP_X_CSRFTOKEN=token,
                HTTP_ORIGIN="https://localhost",
            )
            if response.status_code != 200:
                raise CommandError("Synthetic login failed")
            return browser

        owner, outsider = login(fixture["owner"]), login(fixture["outsider"])
        if owner.get(base + f"products/{fixture['product_id']}/", secure=True).status_code != 200:
            raise CommandError("Restored product access failed")
        response = owner.get(base + f"imports/{fixture['source_id']}/file/", secure=True)
        data = b"".join(response.streaming_content) if response.streaming else response.content
        if (
            response.status_code != 200
            or hashlib.sha256(data).hexdigest() != fixture["source_sha256"]
        ):
            raise CommandError("Restored private source integrity failed")
        if owner.get(base + "assessments/", secure=True).json() != fixture["assessments"]:
            raise CommandError("Immutable assessment snapshot changed")
        for path in (
            base + f"products/{fixture['product_id']}/",
            base + f"imports/{fixture['source_id']}/file/",
            base + "assessments/",
        ):
            if outsider.get(path, secure=True).status_code != 404:
                raise CommandError("Restored tenant/revocation boundary failed")
        self.stdout.write(
            json.dumps(
                {
                    "status": "passed",
                    "real_logins": 2,
                    "private_integrity": True,
                    "tenant_denials": 3,
                    "immutable_assessments": fixture["assessments"]["count"],
                    "runtime_role_privileged": False,
                }
            )
        )
