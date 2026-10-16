"""Controlled security-dependency outage in an isolated local rehearsal; always restart scanner."""

import json
import os
import ssl
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from phase2_smoke import Browser
from phase4_smoke import upload
from release import ROOT, compose, run, write_json


def main():
    folder = Path(os.environ["PPI_REHEARSAL_DIRECTORY"]).resolve()
    assert folder.is_relative_to(ROOT / "artifacts")
    manifest = json.loads((folder / "release.json").read_text())
    command = compose(folder, manifest)
    origin = os.environ["PPI_SMOKE_ORIGIN"]
    assert origin.startswith("https://127.0.0.1:")
    ctx = ssl.create_default_context(cafile=str(folder / "ca.crt"))
    fixture = json.loads((folder / "journey.json").read_text())
    browser = Browser()
    browser.request("/api/v1/auth/login/", data=fixture["owner"])
    base = f"/api/v1/organizations/{fixture['organization_id']}/imports/"
    before = browser.request(base)["count"]
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    assert len(eicar) == 68
    upload(browser, base, eicar, expected=400)
    assert browser.request(base)["count"] == before

    def health(route):
        try:
            response = urlopen(
                Request(origin + route, headers={"X-Request-ID": "phase8-scanner-outage"}),
                context=ctx,
                timeout=5,
            )
        except HTTPError as error:
            response = error
        with response:
            return response.status

    try:
        run(command + ["stop", "scanner"], timeout=60)
        assert health("/api/v1/health/ready/") == 503
        assert health("/api/v1/health/live/") == 200
        upload(browser, base, b"sku,name\nOUTAGE,Rejected synthetic upload\n", expected=400)
        assert browser.request(base)["count"] == before
    finally:
        run(
            command + ["up", "-d", "--wait", "--wait-timeout", "240", "scanner"],
            timeout=300,
        )
    assert health("/api/v1/health/ready/") == 200
    logs = run(command + ["logs", "--no-color", "--tail", "100", "backend"])
    assert "readiness_unavailable" in logs and "phase8-scanner-outage" in logs
    result = {
        "status": "passed",
        "real_eicar_rejected": True,
        "outage_upload_rejected": True,
        "readiness_during_outage": 503,
        "liveness_during_outage": 200,
        "recovered_readiness": 200,
        "redacted_failure_signal_observed": True,
        "scanner_version": run(command + ["exec", "-T", "scanner", "clamdscan", "--version"]),
    }
    write_json(folder / "security.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
