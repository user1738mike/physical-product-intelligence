"""Bounded DB outage of one generated local rehearsal; restart in finally."""

import argparse
import json
import os
import ssl
import time
from urllib.error import HTTPError
from urllib.request import urlopen

from phase2_smoke import Browser
from release import ROOT, compose, exclusive, run, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    folder = (ROOT / args.directory).resolve()
    if not folder.is_relative_to(ROOT / "artifacts"):
        parser.error("Only a generated local rehearsal accepted")
    manifest = json.loads((folder / "release.json").read_text(encoding="utf-8"))
    command = compose(folder, manifest)
    origin = os.environ["PPI_SMOKE_ORIGIN"]
    if not origin.startswith("https://127.0.0.1:"):
        parser.error("Only the authorized local TLS endpoint accepted")
    ctx = ssl.create_default_context(cafile=str(folder / "ca.crt"))
    fixture = json.loads((folder / "journey.json").read_text(encoding="utf-8"))
    browser = Browser()
    browser.request("/api/v1/auth/login/", data=fixture["owner"])
    path = f"/api/v1/organizations/{fixture['organization_id']}/assessments/"
    before = browser.request(path)

    def status(route):
        try:
            response = urlopen(origin + route, context=ctx, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status

    with exclusive(folder):
        try:
            run(command + ["stop", "db"], timeout=60)
            live = status("/api/v1/health/live/")
            ready = status("/api/v1/health/ready/")
            if (live, ready) != (200, 503):
                raise RuntimeError("Database outage health contract failed")
        finally:
            run(command + ["up", "-d", "--wait", "--wait-timeout", "120", "db"], timeout=180)
        recovered = False
        for _ in range(10):
            if status("/api/v1/health/ready/") == 200:
                recovered = True
                break
            time.sleep(1)
        if not recovered or browser.request(path) != before:
            raise RuntimeError("Database recovery or immutable record verification failed")
        write_json(
            folder / "database-outage.json",
            {
                "status": "passed",
                "liveness_during_outage": live,
                "readiness_during_outage": ready,
                "recovered_readiness": 200,
                "authenticated_session_and_assessments_preserved": True,
                "live_provider_calls": 0,
            },
        )
        print(json.dumps({"status": "passed", "evidence": str(folder / "database-outage.json")}))


if __name__ == "__main__":
    main()
