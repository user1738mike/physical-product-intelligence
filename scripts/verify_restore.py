"""Synthetic recovery drill. Creates two NEW databases; never drops/overwrites any database."""

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def restored_checks():
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from rest_framework.test import APIClient

    from ingestion.models import ImportJob
    from ingestion.storage import read_upload
    from organizations.models import Organization
    from products.models import Product

    owner = get_user_model().objects.get(username="equipment-owner")
    outsider = get_user_model().objects.get(username="equipment-outsider")
    org = Organization.objects.get(slug="equipment-lab")
    product = Product.objects.get(sku="FIT-001", organization=org)
    job = ImportJob.objects.get(organization=org)
    assert read_upload(job) == b"sku,name\nDRILL,Synthetic recovery fixture\n"
    client = APIClient()
    client.force_authenticate(owner)
    base = f"/api/v1/organizations/{org.pk}/"
    assert client.get(base + f"products/{product.pk}/").status_code == 200
    response = client.get(base + f"imports/{job.pk}/file/")
    assert response.status_code == 200
    contents = b"".join(response.streaming_content) if response.streaming else response.content
    assert contents == read_upload(job)
    response.close()
    client.force_authenticate(outsider)
    assert client.get(base + f"products/{product.pk}/").status_code == 404
    assert client.get(base + f"imports/{job.pk}/file/").status_code == 404
    assert client.get(base + "assessments/").status_code == 404
    call_command("migrate", check=True, verbosity=0)
    print(
        json.dumps(
            {
                "restored_tenant_denials": 3,
                "authorized_reads": 2,
                "file_integrity": True,
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-create-isolated-data", action="store_true")
    parser.add_argument("--pg-bin", type=Path)
    parser.add_argument("--verify-restored", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "backend"))
    if args.verify_restored:
        restored_checks()
        return
    if not args.allow_create_isolated_data or not args.pg_bin:
        parser.error(
            "Explicit fixture creation and a matching PostgreSQL client directory required"
        )
    import psycopg
    from psycopg import sql

    # The configured server must be the operator's disposable drill server, never production.
    token = secrets.token_hex(5)
    source, target = "ppi_drill_" + token, "ppi_restore_" + token
    work = ROOT / "artifacts" / ("phase7-recovery-" + token)
    work.mkdir(mode=0o700, parents=True)
    with psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        user=os.environ.get("POSTGRES_USER", "ppi"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        dbname="postgres",
        autocommit=True,
    ) as db:
        for name in (source, target):
            db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    os.environ.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings.test",
            "POSTGRES_DB": source,
            "INGESTION_STORAGE_ROOT": str(work / "source-private"),
            "AI_EXTRACTION_ENABLED": "false",
        }
    )
    import django

    django.setup()
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.core.management import call_command

    from compatibility import services
    from compatibility.tests import Fixture
    from ingestion.services import upload

    call_command("migrate", interactive=False, verbosity=0)
    fixture = Fixture()
    fixture.setup_fixture()
    fixture.activate()
    services.assess(fixture.owner, fixture.org.pk, fixture.assessment_data())
    upload(
        fixture.owner,
        fixture.org.pk,
        SimpleUploadedFile(
            "synthetic.csv",
            b"sku,name\nDRILL,Synthetic recovery fixture\n",
            content_type="text/csv",
        ),
    )
    started = time.monotonic()
    extension = ".exe" if os.name == "nt" else ""
    call_command(
        "backup_bundle",
        output=str(work / "bundle"),
        confirm_database=source,
        pg_dump=str(args.pg_bin / ("pg_dump" + extension)),
        maintenance_window=True,
    )
    env = {
        **os.environ,
        "POSTGRES_DB": target,
        "INGESTION_STORAGE_ROOT": str(work / "restored-private"),
    }
    subprocess.run(
        [
            sys.executable,
            "manage.py",
            "restore_bundle",
            "--bundle",
            str(work / "bundle"),
            "--confirm-target-database",
            target,
            "--media-target",
            env["INGESTION_STORAGE_ROOT"],
            "--pg-restore",
            str(args.pg_bin / ("pg_restore" + extension)),
        ],
        cwd=ROOT / "backend",
        env=env,
        check=True,
        timeout=180,
    )
    subprocess.run([sys.executable, __file__, "--verify-restored"], env=env, check=True, timeout=60)
    print(
        json.dumps(
            {
                "status": "isolated_recovery_drill_passed",
                "source_database": source,
                "target_database": target,
                "artifacts": str(work),
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "preserved": "both databases and all bundles; nothing deleted",
            }
        )
    )


if __name__ == "__main__":
    main()
