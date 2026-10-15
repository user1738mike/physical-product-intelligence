"""Disabled-provider integration only. Never invokes a model or enables AI."""

import uuid


def intelligence_disabled_workflow(owner, member, organization_id, foreign_id):
    base = f"/api/v1/organizations/{organization_id}/imports/"
    capabilities = owner.request(base + "ai-capabilities/")
    assert capabilities["available"] is False, (
        "This smoke requires AI disabled; it will not invoke a live provider."
    )
    assert member.request(base + "ai-capabilities/")["available"] is False
    jobs = owner.request(base)
    source = next(job for job in jobs["results"] if job["mode"] == "deterministic")
    product = owner.request(f"/api/v1/organizations/{organization_id}/products/?status=active")[
        "results"
    ][0]
    payload = {"request_id": str(uuid.uuid4()), "product_id": product["id"]}
    owner.request(base + source["id"] + "/extractions/", data=payload, expected=503)
    member.request(base + source["id"] + "/extractions/", data=payload, expected=403)
    owner.request(
        f"/api/v1/organizations/{foreign_id}/imports/{source['id']}/extractions/",
        data=payload,
        expected=404,
    )
    assert owner.request(base)["count"] == jobs["count"]
    print(
        "PASS intelligence proxy: disabled provider, safe fallback, role/tenant denial; "
        "zero jobs created and no live provider call"
    )
