"""Bounded local HTTPS verification/load; no provider calls, remote targets or secret output."""

import argparse
import hashlib
import json
import math
import os
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from phase2_smoke import Browser
from release import ROOT, compose, run, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--load", action="store_true")
    parser.add_argument("--observe-seconds", type=int, default=0, choices=range(0, 61))
    args = parser.parse_args()
    folder = args.directory.resolve()
    assert folder.is_relative_to(ROOT / "artifacts")
    origin = os.environ["PPI_SMOKE_ORIGIN"]
    assert origin.startswith("https://127.0.0.1:")
    ctx = ssl.create_default_context(cafile=str(folder / "ca.crt"))
    fixture = json.loads((folder / "journey.json").read_text())
    browser = Browser()
    browser.request("/api/v1/auth/login/", data=fixture["owner"])
    root = f"/api/v1/organizations/{fixture['organization_id']}/"
    assert browser.request(root + "assessments/") == fixture["assessments"]
    browser.request(f"/api/v1/organizations/{fixture['foreign_id']}/", expected=404)
    with browser.http.open(
        origin + root + f"imports/{fixture['source_id']}/file/", timeout=10
    ) as response:
        assert hashlib.sha256(response.read()).hexdigest() == fixture["source_sha256"]
    # Header spoofing cannot override actual Host or approved browser origin.
    try:
        urlopen(
            Request(origin + "/api/v1/health/live/", headers={"Host": "evil.invalid"}),
            context=ctx,
            timeout=5,
        )
        raise AssertionError("Untrusted Host accepted")
    except HTTPError as error:
        assert error.code == 400
    result = {
        "status": "passed",
        "tls": "CA_and_hostname_verified",
        "private_integrity": True,
        "immutable_assessments": fixture["assessments"]["count"],
        "host_denial": True,
    }
    if args.observe_seconds:
        started = time.monotonic()
        samples = []
        while time.monotonic() - started < args.observe_seconds:
            with urlopen(origin + "/api/v1/health/ready/", context=ctx, timeout=5) as response:
                assert response.status == 200
                assert "max-age=" in response.headers["Strict-Transport-Security"]
                assert "no-store" in response.headers["Cache-Control"]
                samples.append(
                    {
                        "elapsed_seconds": round(time.monotonic() - started, 2),
                        "readiness": response.status,
                    }
                )
            time.sleep(min(2, max(0, args.observe_seconds - (time.monotonic() - started))))
        result["observation"] = {
            "planned_seconds": args.observe_seconds,
            "samples": samples,
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    if args.load:
        cookie = "; ".join(f"{c.name}={c.value}" for c in browser.cookies)
        planned = {
            "requests": 240,
            "concurrency": 4,
            "max_seconds": 30,
            "provisional_p95_ms_max": 1500,
            "provisional_error_rate_max": 0,
        }
        started = time.monotonic()

        def one(_):
            if time.monotonic() - started > 30:
                return None
            at = time.monotonic()
            try:
                with urlopen(
                    Request(origin + root + "products/", headers={"Cookie": cookie}),
                    context=ctx,
                    timeout=5,
                ) as response:
                    response.read()
                    passed = response.status == 200
            except (OSError, HTTPError):
                passed = False
            return (time.monotonic() - at) * 1000, passed

        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = [row for row in pool.map(one, range(240)) if row is not None]
        elapsed = time.monotonic() - started
        latencies = sorted(row[0] for row in rows)
        errors = sum(not row[1] for row in rows)
        result["load"] = {
            "planned": planned,
            "completed": len(rows),
            "errors": errors,
            "error_rate": errors / len(rows),
            "elapsed_seconds": round(elapsed, 3),
            "throughput_rps": round(len(rows) / elapsed, 2),
            "p50_ms": round(latencies[math.ceil(0.50 * len(rows)) - 1], 2),
            "p95_ms": round(latencies[math.ceil(0.95 * len(rows)) - 1], 2),
            "p99_ms": round(latencies[math.ceil(0.99 * len(rows)) - 1], 2),
        }
        manifest = json.loads((folder / "release.json").read_text())
        command = compose(folder, manifest)
        names = run(command + ["ps", "--format", "{{.Name}}"]).splitlines()
        result["load"]["resource_sample"] = [
            json.loads(line)
            for line in run(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}", *names]
            ).splitlines()
        ]
        result["load"]["hardware"] = run(
            [
                "docker",
                "info",
                "--format",
                "Docker CPUs={{.NCPU}} memory_bytes={{.MemTotal}}",
            ]
        )
        result["load"]["operational_status"] = json.loads(
            run(command + ["exec", "-T", "backend", "python", "manage.py", "operational_status"])
        )
        result["load"]["targets_passed"] = (
            len(rows) == planned["requests"]
            and elapsed <= planned["max_seconds"]
            and errors == 0
            and result["load"]["p95_ms"] <= 1500
        )
        if not result["load"]["targets_passed"]:
            result["status"] = "failed"
    name = (
        "load.json" if args.load else "observation.json" if args.observe_seconds else "access.json"
    )
    write_json(folder / name, result)
    print(
        json.dumps(
            result
            if not args.load
            else {
                **result,
                "load": {
                    key: value
                    for key, value in result["load"].items()
                    if key not in {"resource_sample"}
                },
            }
        )
    )
    if args.load and not result["load"]["targets_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
