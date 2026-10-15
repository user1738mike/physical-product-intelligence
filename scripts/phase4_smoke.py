"""Ingestion coverage reused by Phase 3's authenticated disposable smoke accounts."""

import json
import secrets
from urllib.error import HTTPError
from urllib.request import Request

from phase2_smoke import ORIGIN


def upload(browser, path, payload, *, csrf=True, expected=201):
    boundary = "ppi-" + secrets.token_hex(12)
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            'filename="source.csv"\r\n'
            "Content-Type: text/csv\r\n\r\n"
        ).encode()
        + payload
        + f"\r\n--{boundary}--\r\n".encode()
    )
    headers = {
        "Origin": ORIGIN,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    if csrf:
        headers["X-CSRFToken"] = browser.request("/api/v1/auth/csrf/")["csrfToken"]
    try:
        response = browser.http.open(Request(ORIGIN + path, data=body, headers=headers), timeout=30)
    except HTTPError as error:
        response = error
    with response:
        assert response.status == expected, f"Upload expected {expected}, got {response.status}"
        assert "no-store" in response.headers.get("Cache-Control", "")
        return json.loads(response.read())


def ingestion_workflows(owner, member, organization_id, foreign_id):
    base = f"/api/v1/organizations/{organization_id}/imports/"
    upload(owner, base, b"sku,name\nA,Box\n", csrf=False, expected=403)
    large = upload(owner, base, b"sku,name,notes\n" + b"UNUSED,Fixture," + b"x" * 70000 + b"\n")
    owner.request(base + f"{large['id']}/cancel/", data={"expected_version": large["version"]})
    payload = (
        b"sku,name,package_name,package_type,mass,mass_unit\nIMPORT-"
        + secrets.token_hex(6).encode()
        + b",Imported carton,Shipping case,case,1350,g\n"
    )
    job = upload(owner, base, payload)
    path = base + f"{job['id']}/"
    job = owner.request(
        path + "validate/", data={"expected_version": job["version"], "delimiter": ","}
    )
    assert job["preview"]["row_count"] == 1
    job = owner.request(
        path + "mapping/",
        data={
            "expected_version": job["version"],
            "mapping": {
                field: field
                for field in [
                    "sku",
                    "name",
                    "package_name",
                    "package_type",
                    "mass",
                    "mass_unit",
                ]
            },
        },
    )
    job = owner.request(path + "process/", data={"expected_version": job["version"]})
    owner.request(path + "apply/", data={"expected_version": job["version"]}, expected=400)
    row = owner.request(path + "rows/")["results"][0]
    owner.request(
        path + f"rows/{row['id']}/creation/",
        data={"allow_create": True, "reason": "Smoke review new product"},
    )
    candidates = owner.request(path + "candidates/")["results"]
    member.request(path + "apply/", data={"expected_version": job["version"]}, expected=403)
    for candidate in candidates:
        owner.request(
            path + f"candidates/{candidate['id']}/review/",
            data={
                "expected_version": candidate["version"],
                "decision": "approve",
                "select_value": candidate["field"] == "mass",
                "reason": "Compared source and explicitly selected reported mass",
            },
        )
    job = owner.request(path)
    applied = owner.request(path + "apply/", data={"expected_version": job["version"]})
    assert applied["status"] == "completed"
    assert applied["counters"]["created_products"] == 1
    assert owner.request(path + "apply/", data={"expected_version": job["version"]}) == applied
    row = owner.request(path + "rows/")["results"][0]
    product_path = f"/api/v1/organizations/{organization_id}/products/{row['product_id']}/"
    claim = owner.request(product_path + f"packaging/{row['packaging_id']}/claims/")["results"][0]
    assert claim["basis"] == "reported" and claim["canonical_value"] == "1.350000000"
    assert claim["evidence"]["capture_status"] == "stored_private"
    assert claim["evidence"]["source_artifact"]["job_id"] == job["id"]
    with owner.http.open(ORIGIN + path + "file/", timeout=20) as response:
        assert response.read() == payload
        assert "attachment" in response.headers["Content-Disposition"]
        assert response.headers["X-Content-Type-Options"] == "nosniff"
    member.request(path + "errors/")
    owner.request(f"/api/v1/organizations/{foreign_id}/imports/{job['id']}/file/", expected=404)
    assert owner.request(path + "history/")["count"] >= len(candidates)
    print(
        "PASS ingestion proxy: multipart >64KiB, CSRF, mapping, private source, review roles, "
        "provenance, atomic idempotent apply and nested tenant denial"
    )
