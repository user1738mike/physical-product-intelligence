"""Operator-only logical backup bundles. Restore requires a separate empty database/root."""

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.files.storage import storages
from django.db import connection


def counts():
    return {
        m._meta.label: m.objects.count()
        for m in apps.get_models()
        if m._meta.label != "operations.RateBucket"
    }


def safe_path(root, key):
    if not re.fullmatch(r"[a-f0-9-]{36}/[a-f0-9]{32}\.(csv|xlsx|pdf|txt)", key):
        raise ValueError("Invalid private storage key")
    path = root / key
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError("Unsafe archive path")
    return path


def pg_tool(executable, args):
    db = settings.DATABASES["default"]
    env = {
        key: os.environ[key]
        for key in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "PGSSLROOTCERT", "PGSSLMODE")
        if key in os.environ
    }
    env["PGPASSWORD"] = db.get("PASSWORD", "")
    for option, variable in (("sslmode", "PGSSLMODE"), ("sslrootcert", "PGSSLROOTCERT")):
        if db.get("OPTIONS", {}).get(option):
            env[variable] = db["OPTIONS"][option]
    subprocess.run(
        [
            executable,
            "-h",
            db["HOST"],
            "-p",
            str(db["PORT"]),
            "-U",
            db["USER"],
            "-d",
            db["NAME"],
            *args,
        ],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=180,
        check=True,
    )


def backup(output, confirmed, executable):
    if confirmed != connection.settings_dict["NAME"]:
        raise ValueError("Database identity confirmation required")
    root = Path(output).resolve()
    root.mkdir(mode=0o700)  # Refuse existing output, including partial/previous backups.
    dump = root / "database.dump"
    pg_tool(executable, ["--format=custom", "--no-owner", "--no-acl", "--file", str(dump)])
    dump.chmod(0o600)
    from ingestion.models import ImportJob
    from ingestion.storage import read_upload

    uploads = []
    private = root / "private"
    private.mkdir(mode=0o700)
    for job in ImportJob.objects.filter(mode="deterministic").iterator():
        data = read_upload(job)
        target = safe_path(private, job.storage_key)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
        target.chmod(0o600)
        uploads.append({"key": job.storage_key, "sha256": job.sha256, "size": job.size})
    manifest = {
        "format": "ppi-backup-v1",
        "status": "backup_created_not_restore_verified",
        "source_database": confirmed,
        "counts": counts(),
        "dump_sha256": file_sha256(dump),
        "uploads": uploads,
    }
    path = root / "manifest.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
    path.chmod(0o600)
    return {
        "status": manifest["status"],
        "models": len(manifest["counts"]),
        "private_files": len(uploads),
    }


def restore(bundle, confirmed, media_target, executable):
    root = Path(bundle).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    database = connection.settings_dict["NAME"]
    if (
        manifest.get("format") != "ppi-backup-v1"
        or confirmed != database
        or confirmed == manifest["source_database"]
        or not re.fullmatch(r"ppi_restore_[a-z0-9_]{1,40}", confirmed)
    ):
        raise ValueError("Restore requires an explicitly named isolated ppi_restore_ database")
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        if cursor.fetchone()[0] != 0:
            raise ValueError("Restore target must be empty; overwrite is forbidden")
    target = Path(media_target).resolve()
    configured = Path(storages["ingestion"].location).resolve()
    if target != configured or target.exists():
        raise ValueError("Private restore root must equal configured storage and must not exist")
    dump = root / "database.dump"
    if dump.is_symlink() or file_sha256(dump) != manifest["dump_sha256"]:
        raise ValueError("Backup dump integrity failure")
    for item in manifest["uploads"]:
        path = safe_path(root / "private", item["key"])
        data = path.read_bytes()
        if len(data) != item["size"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Private source integrity failure")
    target.mkdir(mode=0o700, parents=True)
    pg_tool(executable, ["--exit-on-error", "--no-owner", "--no-acl", str(dump)])
    connection.close()
    if counts() != manifest["counts"]:
        raise ValueError("Restored record counts differ; target remains quarantined")
    for item in manifest["uploads"]:
        path = safe_path(target, item["key"])
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(safe_path(root / "private", item["key"]), path)
        path.chmod(0o600)
    from ingestion.models import ImportJob
    from ingestion.storage import read_upload

    for job in ImportJob.objects.filter(mode="deterministic").iterator():
        read_upload(job)
    return {
        "status": "isolated_restore_verified",
        "models": len(manifest["counts"]),
        "private_files": len(manifest["uploads"]),
    }


def file_sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
