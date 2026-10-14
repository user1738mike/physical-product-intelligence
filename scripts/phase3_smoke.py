"""Verify tenant product APIs through Next.js using a disposable database only."""

import argparse
import secrets

from phase2_smoke import Browser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-create-test-data", action="store_true", required=True)
    parser.parse_args()
    fixtures = []
    for _ in range(2):
        browser = Browser()
        username = "product-smoke-" + secrets.token_hex(8)
        credentials = {"username": username, "password": secrets.token_hex(24)}
        profile = browser.request(
            "/api/v1/auth/register/", data=credentials, expected=201
        )
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
    second, other_profile, _, other_collection, other_base, other_source = fixtures[1]
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
        "PASS product proxy: tenant SKU, evidence provenance, immutable packaging revisions, exact units, CSRF, isolation, roles, archival, revocation and logout"
    )


if __name__ == "__main__":
    main()
