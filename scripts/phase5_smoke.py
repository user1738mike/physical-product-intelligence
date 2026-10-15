"""Deterministic assessment coverage using Phase 3's disposable authenticated tenants."""

import secrets
import uuid


def compatibility_workflows(owner, member, organization_id, foreign_id):
    root = f"/api/v1/organizations/{organization_id}/"
    equipment = owner.request(
        root + "equipment/",
        data={
            "code": "FIT-" + secrets.token_hex(5),
            "name": "Synthetic conveyor fixture",
            "category": "conveyor",
            "operational_context": "Static recorded carton envelope only",
            "supported_levels": ["case"],
            "source_reference": "Synthetic smoke manual",
        },
        expected=201,
    )
    eq = root + f"equipment/{equipment['id']}/"
    member.request(
        eq,
        method="PATCH",
        data={
            "expected_version": 1,
            "name": "Denied",
            "reason": "Member edit must fail",
        },
        expected=403,
    )
    definitions = [
        {
            "id": str(uuid.uuid4()),
            "type": "maximum",
            "name": f"Maximum {a}",
            "explanation": "Synthetic documented maximum, inclusive boundary",
            "severity": "hard",
            "enabled": True,
            "attribute": a,
            "limit": "10" if a == "mass" else "1000",
            "unit": "kg" if a == "mass" else "mm",
            "margin": "0",
            "source_reference": "Synthetic smoke manual",
        }
        for a in ("length", "width", "height", "mass")
    ]

    def rules(version, equipment_version):
        return owner.request(
            eq + "rule-sets/",
            data={
                "expected_equipment_version": equipment_version,
                "expected_rule_version": version,
                "name": "Synthetic static fit",
                "reason": "Explicit smoke envelope revision",
                "evidence_policy": "reported_or_measured",
                "rules": definitions,
            },
            expected=201,
        )

    rule_set = rules(0, 1)
    owner.request(
        eq + f"rule-sets/{rule_set['id']}/activate/",
        data={
            "expected_equipment_version": 1,
            "reason": "Reviewed synthetic documented specifications",
        },
    )
    product = owner.request(
        root + "products/",
        data={
            "sku": "ASSESS-" + secrets.token_hex(5),
            "revision": {
                "name": "Synthetic fit carton",
                "change_reason": "Initial smoke fixture",
            },
        },
        expected=201,
    )
    product_path = root + f"products/{product['id']}/"
    package = owner.request(
        product_path + "packaging/",
        data={"name": "Synthetic shipping case", "level": "case"},
        expected=201,
    )
    scope = product_path + f"packaging/{package['id']}/"
    inputs = {
        "request_id": str(uuid.uuid4()),
        "product_id": product["id"],
        "packaging_id": package["id"],
        "equipment_id": equipment["id"],
        "rule_set_id": rule_set["id"],
        "orientation": "as_recorded",
    }
    owner.request(root + "assessments/", data=inputs, csrf=False, expected=403)
    first = owner.request(root + "assessments/", data=inputs, expected=201)
    assert first["overall"] == "indeterminate"
    source = {
        "title": "Synthetic observation",
        "source_type": "manual",
        "source_reference": "Disposable smoke record",
        "attribution": "Test fixture",
        "license": "Synthetic test only",
        "observed_at": "2026-01-01T00:00:00Z",
    }
    width = None
    for a in ("length", "width", "height", "mass"):
        observation = owner.request(
            scope + "claims/",
            data={
                "attribute": a,
                "basis": "reported",
                "value": "1" if a == "mass" else "50",
                "unit": "kg" if a == "mass" else "mm",
                "observed_at": source["observed_at"],
                "source": source,
            },
            expected=201,
        )
        if a == "width":
            width = observation

    def evaluate(rule_id, parent=None):
        return member.request(
            root + "assessments/",
            data={
                **inputs,
                "request_id": str(uuid.uuid4()),
                "rule_set_id": rule_id,
                "parent_id": parent,
            },
            expected=201,
        )

    passed = evaluate(rule_set["id"], first["id"])
    assert passed["overall"] == "compatible"
    owner.request(
        scope + "claims/",
        data={
            "attribute": "width",
            "basis": "reported",
            "value": "5000",
            "unit": "mm",
            "observed_at": source["observed_at"],
            "source": source,
        },
        expected=201,
    )
    assert evaluate(rule_set["id"])["overall"] == "indeterminate"
    owner.request(
        scope + "attributes/width/selection/",
        data={
            "claim_id": width["id"],
            "rationale": "Explicit editorial selection cannot suppress assessment conflict",
        },
        expected=201,
    )
    assert evaluate(rule_set["id"])["overall"] == "indeterminate"
    definitions[1]["limit"] = "1"
    second_rules = rules(1, 2)
    owner.request(
        eq + f"rule-sets/{second_rules['id']}/activate/",
        data={
            "expected_equipment_version": 2,
            "reason": "Reviewed synthetic smaller maximum width",
        },
    )
    failed = evaluate(second_rules["id"], passed["id"])
    assert failed["overall"] == "incompatible"
    assert owner.request(root + f"assessments/{passed['id']}/") == passed
    assert owner.request(root + "assessments/", data=inputs, expected=201) == first
    comparison = owner.request(
        root + f"assessments/{passed['id']}/compare/?other_id={failed['id']}"
    )
    assert comparison["changes"] and comparison["second_result"] == "incompatible"
    owner.request(
        root + f"assessments/{passed['id']}/",
        method="PATCH",
        data={"overall": "compatible"},
        expected=405,
    )
    member.request(
        f"/api/v1/organizations/{foreign_id}/equipment/{equipment['id']}/", expected=404
    )
    assert (
        owner.request(
            root
            + f"assessments/?product_id={product['id']}&equipment_id={equipment['id']}"
        )["count"]
        >= 4
    )
    print(
        "PASS compatibility proxy: draft/activation, missing/compatible/conflicting/incompatible outcomes, evidence policy, immutable snapshots, idempotency, comparison, CSRF and tenant/role denial"
    )
