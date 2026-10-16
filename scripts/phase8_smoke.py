"""Synthetic recorded extraction via authenticated HTTPS; refuses a live provider mode."""

import hashlib
import json
import os
import uuid
from pathlib import Path

from phase4_smoke import upload


def recorded_workflow(owner, member, org, foreign):
    base = f"/api/v1/organizations/{org}/imports/"
    capability = owner.request(base + "ai-capabilities/")
    assert capability["reason"] == "synthetic_rehearsal_only", "Refusing any live provider mode"
    source = upload(owner, base, b"sku,name,notes\nRECORDED,Fixture,Weight: 1200 g\n")
    assert source["scan_status"] == "clean"
    product = owner.request(f"/api/v1/organizations/{org}/products/?status=active")["results"][0]
    payload = {"request_id": str(uuid.uuid4()), "product_id": product["id"]}
    extraction = base + source["id"] + "/extractions/"
    member.request(extraction, data=payload, expected=403)
    job = owner.request(extraction, data=payload, expected=201)
    assert owner.request(extraction, data=payload, expected=201)["id"] == job["id"]
    path = base + job["id"] + "/"
    job = owner.request(path + "ai-process/", data={"expected_version": job["version"]})
    candidates = owner.request(path + "candidates/")["results"]
    assert len(candidates) == 1
    candidate = candidates[0]
    member.request(
        path + f"candidates/{candidate['id']}/review/",
        data={
            "expected_version": candidate["version"],
            "decision": "approve",
            "reason": "Denied",
        },
        expected=403,
    )
    owner.request(
        path + f"candidates/{candidate['id']}/review/",
        data={
            "expected_version": candidate["version"],
            "decision": "approve",
            "reason": "Synthetic human review against exact source",
            "select_value": True,
        },
    )
    job = owner.request(path)  # Review advances the parent job's optimistic version.
    owner.request(path + "apply/", data={"expected_version": job["version"]})
    receipt = os.environ.get("PPI_REHEARSAL_CONTEXT")
    if receipt:
        context_path = Path(receipt).resolve()
        assert context_path.is_relative_to(Path(__file__).resolve().parents[1] / "artifacts")
        with owner.http.open(
            f"{os.environ['PPI_SMOKE_ORIGIN']}{base}{source['id']}/file/", timeout=10
        ) as response:
            checksum = hashlib.sha256(response.read()).hexdigest()
        context = {
            "owner": owner.fixture_credentials,
            "outsider": member.fixture_credentials,
            "organization_id": org,
            "foreign_id": foreign,
            "product_id": product["id"],
            "source_id": source["id"],
            "job_id": job["id"],
            "source_sha256": checksum,
            "assessments": owner.request(f"/api/v1/organizations/{org}/assessments/"),
        }
        with context_path.open("x", encoding="utf-8") as stream:
            json.dump(context, stream)
        context_path.chmod(0o600)
    member.request(f"/api/v1/organizations/{foreign}/imports/{job['id']}/", expected=404)
    owner.request(f"/api/v1/organizations/{foreign}/imports/{source['id']}/file/", expected=404)
    print(
        "PASS recorded extraction: scanner, duplicate start, human review/selection, apply, "
        "tenant/role denial; zero provider requests"
    )
