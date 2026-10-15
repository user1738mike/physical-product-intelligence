"""Validate production settings using synthetic configuration; no credential/provider access."""

import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env = {
    key: value
    for key, value in os.environ.items()
    if key
    in {
        "SYSTEMROOT",
        "WINDIR",
        "PATH",
        "TEMP",
        "TMP",
        "VIRTUAL_ENV",
        "PYTHONHOME",
    }
}
env.update(
    {
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": secrets.token_hex(40),
        "DJANGO_ALLOWED_HOSTS": "api.example.invalid",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://app.example.invalid",
        "DJANGO_HSTS_INCLUDE_SUBDOMAINS": "true",
        "DJANGO_HSTS_PRELOAD": "true",
        "POSTGRES_DB": "synthetic_settings_only",
        "POSTGRES_USER": "synthetic_settings_only",
        "POSTGRES_PASSWORD": secrets.token_hex(32),
        "POSTGRES_HOST": "db.example.invalid",
        "POSTGRES_PORT": "5432",
        "AI_EXTRACTION_ENABLED": "false",
        "INGESTION_STORAGE_ROOT": str(Path(tempfile.gettempdir()) / "ppi-config-fixture"),
    }
)
subprocess.run(
    [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
    cwd=ROOT / "backend",
    env=env,
    check=True,
    timeout=30,
)
