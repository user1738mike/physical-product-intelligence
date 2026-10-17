"""Import into a fresh cache, binding official TLS metadata, archive and database checksums."""

import argparse
import json
import re
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path

from grype_provenance import METADATA_URL, cache_digest, digest, validate_metadata
from release import ROOT, image, write_json
from release_scan import execute, fresh_database


def stop_owned_import(name, nonce):
    rc, label, _ = execute(
        [
            "docker",
            "inspect",
            "--type",
            "container",
            "--format",
            '{{ index .Config.Labels "ppi.grype-import" }}',
            name,
        ],
        timeout=20,
    )
    if rc == 0 and label.strip() == nonce:
        execute(["docker", "stop", "--time", "5", name], timeout=20)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python-image", default="physical-product-intelligence-backend")
    args = parser.parse_args()
    if not re.fullmatch(r"ppi_grype_[a-f0-9]{10}", args.cache):
        parser.error("Choose a new ppi_grype_ followed by ten hexadecimal characters cache name")
    archive, output = args.archive.resolve(), args.output.resolve()
    if not all(path.is_relative_to(ROOT / "artifacts") for path in (archive, output)):
        parser.error("Only ignored project evidence paths accepted")
    if output.exists():
        parser.error("Preserve existing provenance receipts; choose a new output")
    try:
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if not curl:
            raise ValueError()
        rc, body, _ = execute(
            [
                curl,
                "--fail",
                "--show-error",
                "--silent",
                "--max-time",
                "30",
                "--max-filesize",
                "32768",
                "--proto",
                "=https",
                METADATA_URL,
            ],
            timeout=40,
        )
        if rc or len(body) > 32768:
            raise ValueError()
        metadata = json.loads(body)
        validate_metadata(metadata)
        if "sha256:" + digest(archive) != metadata["checksum"]:
            raise ValueError()
        scanner = image("anchore/grype:v0.120.1")
        listed, volumes, _ = execute(["docker", "volume", "ls", "--format", "{{.Name}}"])
        if listed or args.cache in volumes.splitlines():
            raise ValueError("Preserve existing caches")
        # A fresh import is essential: a separately valid local DB plus a valid
        # archive does not prove that their contents are the same.
        nonce = secrets.token_hex(16)
        name = "ppi-grype-import-" + nonce[:16]
        try:
            imported, _, _ = execute(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--name",
                    name,
                    "--label",
                    "ppi.grype-import=" + nonce,
                    "--network",
                    "none",
                    "--memory",
                    "2g",
                    "--cpus",
                    "2",
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
                    args.cache + ":/cache",
                    "-v",
                    str(archive) + ":/official-db.tar.zst:ro",
                    scanner,
                    "db",
                    "import",
                    "/official-db.tar.zst",
                ],
                timeout=900,
            )
        finally:
            stop_owned_import(name, nonce)
        if imported or "sha256:" + digest(archive) != metadata["checksum"]:
            raise ValueError()
        database = cache_digest(args.cache, image(args.python_image), execute)
        rc, status, _ = execute(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "-e",
                "GRYPE_DB_CACHE_DIR=/cache",
                "-e",
                "GRYPE_DB_AUTO_UPDATE=false",
                "-e",
                "GRYPE_DB_MAX_ALLOWED_BUILT_AGE=48h",
                "-e",
                "GRYPE_DB_VALIDATE_AGE=true",
                "-e",
                "GRYPE_DB_VALIDATE_BY_HASH_ON_START=true",
                "-v",
                args.cache + ":/cache",
                scanner,
                "db",
                "status",
            ],
            timeout=300,
        )
        if (
            rc
            or not fresh_database(status)
            or database["client_version"] != metadata["schemaVersion"]
        ):
            raise ValueError()
        receipt = {
            "format": "ppi-official-grype-import-v1",
            "verified_at": datetime.now(UTC).isoformat(),
            "metadata_url": METADATA_URL,
            "metadata": metadata,
            "scanner": scanner,
            "cache": args.cache,
            "archive": archive.relative_to(ROOT).as_posix(),
            "database": database,
            "fresh_cache_import": True,
            "import_exit_code": imported,
        }
        from grype_provenance import verify_receipt

        if not verify_receipt(
            receipt, cache=args.cache, scanner=scanner, status=status, database=database, root=ROOT
        ):
            raise ValueError()
        write_json(output, receipt)
        print(
            json.dumps(
                {
                    "status": "verified_import",
                    "receipt": str(output),
                    "image_scan_acceptance": "not_executed",
                }
            )
        )
    except Exception:
        parser.exit(
            1,
            "Official import verification failed; retain the scan gate. "
            "Private diagnostics suppressed.\n",
        )


if __name__ == "__main__":
    main()
