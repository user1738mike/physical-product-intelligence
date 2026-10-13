import os

from django.core.exceptions import ImproperlyConfigured


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"Required environment variable is missing: {name}")
    return value


def csv(name, default=""):
    return [value.strip() for value in os.environ.get(name, default).split(",") if value.strip()]


def postgres(strict=False):
    get = required if strict else lambda name: os.environ.get(name, DEFAULTS[name])
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": get("POSTGRES_DB"),
        "USER": get("POSTGRES_USER"),
        "PASSWORD": get("POSTGRES_PASSWORD"),
        "HOST": get("POSTGRES_HOST"),
        "PORT": get("POSTGRES_PORT"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"connect_timeout": 5},
    }


DEFAULTS = {
    "POSTGRES_DB": "ppi",
    "POSTGRES_USER": "ppi",
    "POSTGRES_PASSWORD": "",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
}
