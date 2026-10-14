import os

from .base import *  # noqa: F403
from .environment import postgres

INGESTION_ALLOW_UNSCANNED = True

SECRET_KEY = "test-only-key-not-a-production-secret"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
DATABASES = {"default": postgres()}
if os.environ.get("TEST_SQLITE") == "1":
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
