"""Strict provenance for official databases imported through a working host TLS path."""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

METADATA_URL = "https://grype.anchore.io/databases/v6/latest.json"


def validate_metadata(value, now=None):
    if not isinstance(value, dict) or value.get("status") != "active":
        raise ValueError("Official database metadata rejected")
    if any(
        not isinstance(value.get(key), str)
        for key in ("schemaVersion", "built", "path", "checksum")
    ):
        raise ValueError("Malformed official database metadata")
    version = value.get("schemaVersion", "")
    if not re.fullmatch(r"v6\.\d+\.\d+", version):
        raise ValueError("Unsupported database schema")
    if not re.fullmatch(
        "vulnerability-db_" + re.escape(version) + r"_[A-Za-z0-9_.:-]+\.tar\.zst",
        value.get("path", ""),
    ) or not re.fullmatch(r"sha256:[a-f0-9]{64}", value.get("checksum", "")):
        raise ValueError("Official archive identity rejected")
    built = datetime.fromisoformat(value["built"].replace("Z", "+00:00"))
    if built.tzinfo is None or not timedelta(minutes=-5) <= (
        now or datetime.now(UTC)
    ) - built <= timedelta(hours=48):
        raise ValueError("Official database is outside the freshness policy")
    return "https://grype.anchore.io/databases/v6/" + value["path"]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def cache_digest(cache, python_image, execute):
    if not re.fullmatch(r"ppi_[a-z0-9_]{1,60}", cache):
        raise ValueError("Only a named project security cache is accepted")
    code = (
        "import hashlib,json; from pathlib import Path; p=Path('/cache/6'); "
        "m=p/'import.json'; assert m.stat().st_size<4096; "
        "v=json.loads(m.read_text()); "
        "v['sha256']=hashlib.file_digest((p/'vulnerability.db').open('rb'),'sha256').hexdigest(); "
        "print(json.dumps(v))"
    )
    rc, stdout, _ = execute(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "0:0",
            "--cap-drop",
            "ALL",
            "--read-only",
            "--memory",
            "128m",
            "--cpus",
            "1",
            "--pids-limit",
            "32",
            "-v",
            cache + ":/cache:ro",
            "--entrypoint",
            "python",
            python_image,
            "-c",
            code,
        ],
        timeout=300,
    )
    if rc:
        raise ValueError("Imported database content validation failed")
    return json.loads(stdout)


def verify_receipt(receipt, *, cache, scanner, status, database, root, now=None):
    try:
        metadata = receipt["metadata"]
        validate_metadata(metadata, now)
        verified = datetime.fromisoformat(receipt["verified_at"])
        if verified.tzinfo is None or not timedelta(minutes=-5) <= (
            now or datetime.now(UTC)
        ) - verified <= timedelta(hours=48):
            return False
        archive = (root / receipt["archive"]).resolve()
        if not archive.is_relative_to((root / "artifacts").resolve()) or not archive.is_file():
            return False
        return bool(
            receipt["format"] == "ppi-official-grype-import-v1"
            and receipt["fresh_cache_import"] is True
            and receipt["import_exit_code"] == 0
            and receipt["metadata_url"] == METADATA_URL
            and receipt["scanner"] == scanner
            and receipt["cache"] == cache
            and "sha256:" + digest(archive) == metadata["checksum"]
            and receipt["database"] == database
            and re.fullmatch(r"[a-f0-9]{64}", database["sha256"])
            and database["source"] == "manual import"
            and database["client_version"] == metadata["schemaVersion"]
            and re.search(r"From:\s+manual import\s*(?:\n|$)", status)
            and re.search(r"Schema:\s+" + re.escape(metadata["schemaVersion"]) + r"\s", status)
            and re.search(r"Built:\s+" + re.escape(metadata["built"]) + r"\s", status)
            and re.search(r"Status:\s+valid\b", status)
        )
    except (KeyError, TypeError, ValueError, OSError):
        return False
