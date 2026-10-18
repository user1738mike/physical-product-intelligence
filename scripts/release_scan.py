"""Scan exact local release images with a validated official database no older than 48 hours."""

import argparse
import hashlib
import json
import re
import secrets
import subprocess
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from grype_provenance import cache_digest, verify_receipt
from release import ROOT, compose, image, source_identity, write_json


def archive_identity(path):
    """Docker may identify OCI manifests while Grype identifies their config."""
    with tarfile.open(path) as bundle:

        def read(name, maximum):
            member = bundle.getmember(name)
            if not member.isfile() or member.size > maximum:
                raise ValueError("Invalid exported image metadata")
            return bundle.extractfile(member).read(maximum + 1)

        rows = json.loads(read("manifest.json", 32768))
        if len(rows) != 1:
            raise ValueError("Exactly one exported image required")
        config = read(rows[0]["Config"], 4 * 1024 * 1024)
        value = json.loads(config)
        return "sha256:" + hashlib.sha256(config).hexdigest(), value["rootfs"]["diff_ids"]


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


def verdict(code, report, verified_import=False):
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
    origin = status.get("from", "")
    if status.get("valid") is not True or not (
        isinstance(origin, str)
        and (
            origin.startswith("https://grype.anchore.io/databases/")
            or (origin == "manual import" and verified_import)
        )
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


def stop_owned_scan(name, nonce):
    rc, label, _ = execute(
        [
            "docker",
            "inspect",
            "--type",
            "container",
            "--format",
            '{{ index .Config.Labels "ppi.grype-scan" }}',
            name,
        ],
        timeout=20,
    )
    if rc == 0 and label.strip() == nonce:
        execute(["docker", "stop", "--time", "5", name], timeout=20)


def database_status(base, scanner):
    nonce = secrets.token_hex(16)
    name = "ppi-grype-status-" + nonce[:16]
    try:
        return execute(
            base
            + ["--name", name, "--label", "ppi.grype-scan=" + nonce]
            + [scanner, "db", "status"],
            timeout=300,
        )
    finally:
        stop_owned_scan(name, nonce)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sdk-image", default="ppi-phase8-backend-sdk")
    parser.add_argument("--database-cache", default="ppi_phase8_security_cache")
    parser.add_argument("--official-import-receipt", type=Path)
    parser.add_argument(
        "--rollback-image", help="Explicit reviewed compatible immutable rollback artifact"
    )
    parser.add_argument("--rollback-frontend-image", help="Explicit compatible rollback frontend")
    args = parser.parse_args()
    if not re.fullmatch(r"ppi_[a-z0-9_]{1,60}", args.database_cache):
        parser.error("Only a named project security cache is accepted")
    folder, output = args.directory.resolve(), args.output.resolve()
    if not all(p.is_relative_to(ROOT / "artifacts") for p in (folder, output)):
        parser.error("Rehearsal/evidence must remain in ignored artifacts")
    manifest = json.loads((folder / "release.json").read_text(encoding="utf-8"))
    compose(folder, manifest)
    if set(manifest["images"]) != {"backend", "frontend", "postgres", "ingress", "scanner"} or any(
        not re.fullmatch(r"sha256:[a-f0-9]{64}", ref) for ref in manifest["images"].values()
    ):
        parser.error("All five immutable runtime image identities are required")
    output.mkdir(parents=True, exist_ok=False)
    scanner = image("anchore/grype:v0.120.1")
    base = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--memory",
        "2g",
        "--cpus",
        "2",
        "--pids-limit",
        "64",
        "-e",
        "GRYPE_CHECK_FOR_APP_UPDATE=false",
        "-e",
        "GOMEMLIMIT=768MiB",
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
        args.database_cache + ":/cache",
    ]
    code, stdout, stderr = database_status(base, scanner)
    (output / "database-status.log").write_text(stdout + stderr, encoding="utf-8")
    valid = code == 0 and fresh_database(stdout)
    imported = False
    provenance = None
    if valid and re.search(r"From:\s+manual import\s*(?:\n|$)", stdout):
        valid = False
        if args.official_import_receipt:
            try:
                receipt_path = args.official_import_receipt.resolve()
                if not receipt_path.is_relative_to(ROOT / "artifacts"):
                    raise ValueError()
                receipt = json.loads(receipt_path.read_text())
                database = cache_digest(args.database_cache, image(args.sdk_image), execute)
                imported = verify_receipt(
                    receipt,
                    cache=args.database_cache,
                    scanner=scanner,
                    status=stdout,
                    database=database,
                    root=ROOT,
                )
                valid = imported
                if imported:
                    provenance = {
                        "receipt": str(receipt_path),
                        "sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                        "database_sha256": database["sha256"],
                    }
            except (ValueError, KeyError, OSError):
                valid = False
    references = {**manifest["images"], "backend_sdk": image(args.sdk_image)}
    rollback = args.rollback_image or manifest.get("rollback_image")
    if rollback:
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", rollback):
            parser.error("Rollback must be an explicit immutable reviewed image ID")
        references["rollback"] = image(rollback)
    rollback_frontend = args.rollback_frontend_image or manifest.get("rollback_frontend_image")
    if rollback_frontend:
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", rollback_frontend):
            parser.error("Rollback frontend must be an explicit immutable reviewed image ID")
        references["rollback_frontend"] = image(rollback_frontend)
    results = {}
    archive_cache = "ppi_scan_" + secrets.token_hex(5)
    helper = archive_cache + "_transfer"
    # Windows bind mounts can fail Go archive reads with ENOMEM even when
    # capacity is available. Transfer public archives through Docker's API into
    # an isolated native volume. No daemon socket is exposed to the scanner.
    created, _, _ = execute(
        [
            "docker",
            "create",
            "--name",
            helper,
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--memory",
            "64m",
            "-v",
            archive_cache + ":/scan",
            "--entrypoint",
            "python",
            image(args.sdk_image),
            "-c",
            "pass",
        ]
    )
    if created:
        valid = False
    if not rollback:
        results["rollback"] = {
            "status": "blocked",
            "reason": "compatible_rollback_artifact_not_selected",
        }
    if not rollback_frontend:
        results["rollback_frontend"] = {
            "status": "blocked",
            "reason": "compatible_rollback_frontend_not_selected",
        }
    for name, reference in references.items():
        if not valid:
            results[name] = {
                "image": reference,
                "status": "blocked",
                "reason": "official_database_missing_invalid_or_older_than_48h",
            }
            continue
        archive = output / (name + ".tar")
        saved, _, err = execute(
            ["docker", "save", "--output", str(archive), reference], timeout=300
        )
        if saved:
            results[name] = {"image": reference, "status": "blocked", "reason": "export_failed"}
            continue
        try:
            config_id, layers = archive_identity(archive)
            inspected, layer_text, _ = execute(
                ["docker", "image", "inspect", reference, "--format", "{{json .RootFS.Layers}}"]
            )
            if inspected or layers != json.loads(layer_text):
                raise ValueError("Exported image layers do not match selected immutable image")
        except (ValueError, KeyError, OSError, tarfile.TarError):
            results[name] = {
                "image": reference,
                "status": "blocked",
                "reason": "exported_image_identity_invalid",
            }
            continue
        copied, _, _ = execute(["docker", "cp", str(archive), helper + ":/scan/" + archive.name])
        if copied:
            results[name] = {
                "image": reference,
                "status": "blocked",
                "reason": "native_archive_transfer_failed",
            }
            continue
        nonce = secrets.token_hex(16)
        scan_name = "ppi-grype-scan-" + nonce[:16]
        try:
            rc, body, err = execute(
                base
                + ["--name", scan_name, "--label", "ppi.grype-scan=" + nonce]
                + [
                    "-v",
                    archive_cache + ":/scan:ro",
                    scanner,
                    "docker-archive:/scan/" + archive.name,
                    "--output",
                    "json",
                    "--fail-on",
                    "high",
                ],
                600,
            )
        finally:
            stop_owned_scan(scan_name, nonce)
        (output / (name + ".json")).write_text(body, encoding="utf-8")
        (output / (name + ".log")).write_text(err, encoding="utf-8")
        try:
            report = json.loads(body)
        except ValueError:
            report = None
        bound = (
            isinstance(report, dict)
            and report.get("source", {}).get("target", {}).get("imageID") == config_id
        )
        with archive.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        results[name] = {
            "image": reference,
            "status": verdict(rc, report, imported) if bound else "blocked",
            "archive_config_sha256": config_id,
            "immutable_image_layers_verified": True,
            "scan_config_identity_verified": bound,
            "exit_code": rc,
            "archive_sha256": digest,
        }
    if not created:
        execute(["docker", "rm", helper])
    passed = all(r["status"] == "passed" for r in results.values())
    overall = (
        "passed"
        if passed
        else "failed"
        if any(r["status"] == "failed" for r in results.values())
        else "blocked"
    )
    write_json(
        output / "summary.json",
        {
            "status": overall,
            "source": source_identity(),
            "scanner": scanner,
            "scanner_version": "0.120.1",
            "maximum_db_age_hours": 48,
            "automatic_update": False,
            "database_precheck": valid,
            "database_cache": args.database_cache,
            "archive_cache": archive_cache,
            "official_import_provenance": provenance,
            "coverage": results,
            "suppressed_findings": 0,
        },
    )
    print(
        json.dumps(
            {
                "status": overall,
                "images": len(results),
                "database_precheck": valid,
                "evidence": str(output),
            }
        )
    )
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
