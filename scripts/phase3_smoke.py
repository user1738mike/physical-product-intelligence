"""Verify tenant product APIs through Next.js using a disposable database only."""

import argparse
import os
import secrets

from phase2_smoke import Browser


def catalog_workflows(first, second, base, collection, source, other_base, other_source):
    product = first.request(base)
    edited = first.request(
        base,
        method="PATCH",
        data={
            "name": "Catalog edited fixture",
            "expected_revision": product["latest_revision_number"],
            "change_reason": "Exercise optimistic catalog editing",
        },
    )
    assert edited["latest_revision_number"] == product["latest_revision_number"] + 1
    first.request(
        base,
        method="PATCH",
        data={
            "name": "Stale",
            "expected_revision": product["latest_revision_number"],
            "change_reason": "Must fail",
        },
        expected=409,
    )
    assert (
        first.request(collection + "?search=Catalog%20edited&status=active&ordering=name")["count"]
        == 1
    )
    packing = first.request(
        base + "packaging/",
        data={"name": "Shipping case", "level": "case", "quantity": 6},
        expected=201,
    )
    pack_base = base + f"packaging/{packing['id']}/"
    packing = second.request(
        pack_base,
        method="PATCH",
        data={
            "expected_version": 1,
            "change_reason": "Record material",
            "material": "Cardboard",
        },
    )
    second.request(
        pack_base + "state/",
        data={"expected_version": packing["version"], "is_active": False},
        expected=403,
    )
    packing = first.request(
        pack_base + "state/",
        data={"expected_version": packing["version"], "is_active": False},
    )
    packing = first.request(
        pack_base + "state/",
        data={"expected_version": packing["version"], "is_active": True},
    )
    assert first.request(pack_base + "revisions/")["count"] == 4
    claim = {
        "attribute": "mass",
        "basis": "reported",
        "value": "1200",
        "unit": "g",
        "evidence_id": source["id"],
        "observed_at": "2026-01-01T10:00:00Z",
    }
    reported = second.request(pack_base + "claims/", data=claim, expected=201)
    assert reported["basis"] == "reported" and reported["verification_record"] is None
    estimate = first.request(
        pack_base + "claims/",
        data={
            **claim,
            "basis": "estimated",
            "value": "1100",
            "method": "External model fixture v1",
            "limitations": "Not physically measured",
        },
        expected=201,
    )
    verification = {
        "value": "1.35",
        "unit": "kg",
        "observed_at": "2026-01-02T10:00:00Z",
        "instrument": "Scale fixture 17",
        "procedure": "Tare the scale and weigh the sealed sample.",
        "notes": "One sample; no safety determination.",
        "source": {
            "title": "Physical fixture measurement",
            "source_type": "physical_test",
            "source_reference": "Fixture notebook entry 17",
            "attribution": "Fixture observer",
            "license": "Fixture use only",
            "observed_at": "2026-01-02T10:00:00Z",
        },
    }
    verify_url = pack_base + f"claims/{estimate['id']}/verification/"
    second.request(verify_url, data=verification, expected=403)
    measured = first.request(verify_url, data=verification, expected=201)
    assert measured["basis"] == "measured" and measured["verification_record"]["verified_by_id"]
    assert first.request(pack_base + f"claims/{estimate['id']}/")["basis"] == "estimated"
    state = next(
        row
        for row in first.request(pack_base + "attributes/")["results"]
        if row["attribute"] == "mass"
    )
    assert state["status"] == "conflict" and state["selected_claim"] is None
    selection = {
        "claim_id": measured["id"],
        "rationale": "Prefer the documented physical observation for this sample.",
    }
    second.request(pack_base + "attributes/mass/selection/", data=selection, expected=403)
    first.request(pack_base + "attributes/mass/selection/", data=selection, expected=201)
    state = next(
        row
        for row in first.request(pack_base + "attributes/")["results"]
        if row["attribute"] == "mass"
    )
    assert state["status"] == "resolved" and state["claim_count"] == 3
    assert state["selected_claim"]["canonical_value"] == "1.350000000"
    first.request(pack_base + "claims/", data={**claim, "value": "1350"}, expected=201)
    state = next(
        row
        for row in first.request(pack_base + "attributes/")["results"]
        if row["attribute"] == "mass"
    )
    assert state["status"] == "resolved" and state["selected_claim"]["id"] == measured["id"]
    first.request(pack_base + "claims/", data={**claim, "value": "1400"}, expected=201)
    state = next(
        row
        for row in first.request(pack_base + "attributes/")["results"]
        if row["attribute"] == "mass"
    )
    assert state["status"] == "conflict" and state["selected_claim"] is None
    first.request(
        pack_base + "claims/",
        data={**claim, "evidence_id": other_source["id"]},
        expected=404,
    )
    first.request(other_base + "history/", expected=404)
    first.request(
        other_base + "packaging/",
        data={"name": "Forbidden", "level": "unit"},
        expected=404,
    )
    assert second.request(pack_base + "history/")["count"] >= 5
    assert first.request(base + "history/")["count"] > 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-create-test-data", action="store_true", required=True)
    parser.parse_args()
    fixtures = []
    for _ in range(2):
        browser = Browser()
        username = "product-smoke-" + secrets.token_hex(8)
        credentials = {"username": username, "password": secrets.token_hex(24)}
        browser.fixture_credentials = credentials
        profile = browser.request("/api/v1/auth/register/", data=credentials, expected=201)
        browser.request("/api/v1/auth/login/", data=credentials)
        org = browser.request(
            "/api/v1/organizations/",
            data={"name": "Disposable product tenant", "slug": username},
            expected=201,
        )
        collection = f"/api/v1/organizations/{org['id']}/products/"
        payload = {
            "sku": "SMOKE-001",
            "revision": {"name": "Fixture product", "change_reason": "Initial record"},
        }
        browser.request(collection, data=payload, csrf=False, expected=403)
        product = browser.request(collection, data=payload, expected=201)
        assert product["latest_revision_number"] == 1
        browser.request(collection, data=payload, expected=409)
        base = collection + product["id"] + "/"
        source = browser.request(
            base + "evidence/",
            data={
                "title": "Manual fixture measurement",
                "source_type": "manual",
                "source_reference": "Disposable fixture notebook",
                "attribution": "Smoke observer",
                "license": "Fixture internal use",
                "observed_at": "2026-01-01T10:00:00Z",
                "declared_sha256": "a" * 64,
            },
            expected=201,
        )
        assert source["capture_status"] == "reference_only"
        assert browser.request(base + f"evidence/{source['id']}/") == source
        fixtures.append((browser, profile, org, collection, base, source))

    first, _, org, collection, base, source = fixtures[0]
    second, other_profile, other_org, other_collection, other_base, other_source = fixtures[1]
    first.request(other_collection, expected=404)
    first.request(other_base, expected=404)
    first.request(
        base + "revisions/",
        data={
            "name": "Forbidden source",
            "change_reason": "Cross-tenant fixture",
            "evidence_ids": [other_source["id"]],
        },
        expected=404,
    )
    revision = first.request(
        base + "revisions/",
        data={
            "name": "Measured fixture",
            "change_reason": "Add observed packaging",
            "packaging": [
                {
                    "level": "unit",
                    "quantity": 1,
                    "measurements": [
                        {
                            "property": "mass",
                            "value": "1250",
                            "unit": "g",
                            "lower": "1200",
                            "upper": "1300",
                            "method": "measured",
                            "observed_at": "2026-01-01T10:00:00Z",
                            "evidence_id": source["id"],
                        }
                    ],
                },
                {"level": "case", "contains_level": "unit", "quantity": 12},
            ],
        },
        expected=201,
    )
    assert revision["number"] == 2
    assert revision["evidence_ids"] == [source["id"]]
    profiles = {profile["level"]: profile for profile in revision["packaging"]}
    assert profiles["case"]["contains_id"] == profiles["unit"]["id"]
    assert profiles["unit"]["fragile"] is None
    mass = profiles["unit"]["measurements"][0]
    assert mass["canonical_value"] == "1.250000000"
    assert mass["canonical_lower"] == "1.200000000"
    assert mass["canonical_unit"] == "kg"
    revision_url = base + f"revisions/{revision['id']}/"
    assert first.request(revision_url) == revision
    first.request(revision_url, method="PATCH", data={"name": "Tampered"}, expected=405)
    first.request(base + f"evidence/{other_source['id']}/", expected=404)
    assert first.request(revision_url + "packaging/")["count"] == 2
    first.request(revision_url + f"packaging/{profiles['unit']['id']}/")
    assert first.request(collection)["count"] == 1

    member = first.request(
        f"/api/v1/organizations/{org['id']}/members/",
        data={"username": other_profile["username"]},
        expected=201,
    )
    second.request(
        base + "revisions/",
        data={
            "name": "Member contribution",
            "change_reason": "Member recorded observation",
        },
        expected=201,
    )
    second.request(base + "state/", data={"is_active": False}, expected=403)
    first.request(base + "state/", data={"is_active": False})
    second.request(
        base + "revisions/",
        data={"name": "Archived", "change_reason": "Must fail"},
        expected=400,
    )
    assert first.request(revision_url) == revision
    first.request(base + "state/", data={"is_active": True})
    catalog_workflows(first, second, base, collection, source, other_base, other_source)
    from phase4_smoke import ingestion_workflows

    ingestion_workflows(first, second, org["id"], other_org["id"])
    from phase5_smoke import compatibility_workflows

    compatibility_workflows(first, second, org["id"], other_org["id"])
    from phase6_smoke import intelligence_disabled_workflow

    if os.environ.get("PPI_SMOKE_FIXTURES") == "recorded":
        from phase8_smoke import recorded_workflow

        recorded_workflow(first, second, org["id"], other_org["id"])
    else:
        intelligence_disabled_workflow(first, second, org["id"], other_org["id"])
    first.request(
        f"/api/v1/organizations/{org['id']}/members/{member['id']}/",
        method="DELETE",
        expected=204,
    )
    second.request(base, expected=404)
    events = first.request(f"/api/v1/organizations/{org['id']}/audit/")["results"]
    assert any(event["action"] == "product.revision_created" for event in events)
    first.request("/api/v1/auth/logout/", data={}, expected=204)
    first.request(base, expected=403)
    print(
        "PASS product proxy: catalog search/edit, packaging lifecycle, reported/estimated/verified "
        "claims, conflict selection, exact units, scoped history, CSRF, tenant denial, "
        "revocation and logout"
    )


if __name__ == "__main__":
    main()
