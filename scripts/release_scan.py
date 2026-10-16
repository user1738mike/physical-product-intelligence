"""Scan exact local release images with a validated official database no older than 48 hours."""

import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from release import ROOT, compose, image, source_identity, write_json


def fresh_database(text, now=None):
    match = re.search(r"Built:\s+(\S+)", text)
    if not match or not re.search(r"Status:\s+valid\b", text):
        return False
    try:
        built = datetime.fromisoformat(match[1].replace("Z", "+00:00"))
        age = (now or datetime.now(UTC)) - built
        return timedelta(minutes=-5) <= age <= timedelta(hours=48)
    except (ValueError, TypeError):
        return False


def verdict(code, report):
    if (
        code not in {0, 2}
        or not isinstance(report, dict)
        or not isinstance(report.get("matches"), list)
    ):
        return "blocked"
    if any(
        not isinstance(row, dict)
        or not isinstance(row.get("vulnerability"), dict)
        or "severity" not in row["vulnerability"]
        for row in report["matches"]
    ):
        return "blocked"
    status = report.get("descriptor", {}).get("db", {}).get("status", {})
    if not status.get("valid") or not status.get("from", "").startswith(
        "https://grype.anchore.io/databases/"
    ):
        return "blocked"
    if code == 2 or any(
        row["vulnerability"]["severity"] in {"High", "Critical"} for row in report["matches"]
    ):
        return "failed"
    return "passed"


def execute(command, timeout=120):
    try:
        r = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "Bounded scanner operation timed out."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sdk-image", default="ppi-phase8-backend-sdk")
    args = parser.parse_args()
    folder, output = args.directory.resolve(), args.output.resolve()
    if not all(p.is_relative_to(ROOT / "artifacts") for p in (folder, output)):
        parser.error("Rehearsal/evidence must remain in ignored artifacts")
    manifest = json.loads((folder / "release.json").read_text(encoding="utf-8"))
    compose(folder, manifest)
    output.mkdir(parents=True, exist_ok=False)
    scanner = image("anchore/grype:v0.120.1")
    base = [
        "docker",
        "run",
        "--rm",
        "-e",
        "GRYPE_DB_CACHE_DIR=/cache",
        "-e",
        "GRYPE_DB_AUTO_UPDATE=false",
        "-e",
        "GRYPE_DB_VALIDATE_AGE=true",
        "-e",
        "GRYPE_DB_MAX_ALLOWED_BUILT_AGE=48h",
        "-e",
        "GRYPE_DB_VALIDATE_BY_HASH_ON_START=true",
        "-v",
        "ppi_phase8_security_cache:/cache",
    ]
    code, stdout, stderr = execute(base + [scanner, "db", "status"])
    (output / "database-status.log").write_text(stdout + stderr, encoding="utf-8")
    valid = code == 0 and fresh_database(stdout)
    references = {**manifest["images"], "backend_sdk": image(args.sdk_image)}
    prior = ROOT / "artifacts/phase8-previous/previous.json"
    if prior.exists():
        references["prior_code_rollback"] = json.loads(prior.read_text())["image"]
    results = {}
    for name, reference in references.items():
        if not valid:
            results[name] = {
                "image": reference,
                "status": "blocked",
                "reason": "official_database_missing_invalid_or_older_than_48h",
            }
            continue
        archive = output / (name + ".tar")
        saved, _, err = execute(["docker", "save", "--output", str(archive), reference])
        if saved:
            results[name] = {"image": reference, "status": "blocked", "reason": "export_failed"}
            continue
        rc, body, err = execute(
            base
            + [
                "-v",
                str(output) + ":/scan:ro",
                scanner,
                "docker-archive:/scan/" + archive.name,
                "--output",
                "json",
                "--fail-on",
                "high",
            ],
            600,
        )
        (output / (name + ".json")).write_text(body, encoding="utf-8")
        (output / (name + ".log")).write_text(err, encoding="utf-8")
        try:
            report = json.loads(body)
        except ValueError:
            report = None
        with archive.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        results[name] = {
            "image": reference,
            "status": verdict(rc, report),
            "exit_code": rc,
            "archive_sha256": digest,
        }
    passed = all(r["status"] == "passed" for r in results.values())
    write_json(
        output / "summary.json",
        {
            "status": "passed" if passed else "blocked",
            "source": source_identity(),
            "scanner": scanner,
            "scanner_version": "0.120.1",
            "maximum_db_age_hours": 48,
            "automatic_update": False,
            "database_precheck": valid,
            "coverage": results,
            "suppressed_findings": 0,
        },
    )
    print(
        json.dumps(
            {
                "status": "passed" if passed else "blocked",
                "images": len(results),
                "database_precheck": valid,
                "evidence": str(output),
            }
        )
    )
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
