import base64
import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import STATIC_ROOT
from .environment import csv, postgres, required

SECRET_KEY = required("DJANGO_SECRET_KEY")
if len(SECRET_KEY) < 50 or any(
    marker in SECRET_KEY.lower() for marker in ("replace", "development", "change-me", "test-only")
):
    raise ImproperlyConfigured("Production requires a strong, non-placeholder DJANGO_SECRET_KEY")
ALLOWED_HOSTS = csv("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS or any("*" in host for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("Production requires explicit DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = csv("DJANGO_CSRF_TRUSTED_ORIGINS")
if not CSRF_TRUSTED_ORIGINS or any(
    urlsplit(origin).scheme != "https"
    or not urlsplit(origin).hostname
    or "*" in origin
    or urlsplit(origin).path not in ("", "/")
    or urlsplit(origin).query
    or urlsplit(origin).fragment
    or urlsplit(origin).username
    for origin in CSRF_TRUSTED_ORIGINS
):
    raise ImproperlyConfigured("Production requires explicit HTTPS CSRF origins")
DATABASES = {"default": postgres(strict=True)}
sslmode = os.environ.get("POSTGRES_SSLMODE", "verify-full")
if sslmode != "verify-full":
    raise ImproperlyConfigured("Production database connections require verify-full TLS")
DATABASES["default"]["OPTIONS"]["sslmode"] = sslmode
if os.environ.get("POSTGRES_SSLROOTCERT"):
    DATABASES["default"]["OPTIONS"]["sslrootcert"] = os.environ["POSTGRES_SSLROOTCERT"]
password = DATABASES["default"]["PASSWORD"]
if len(password) < 24 or any(
    marker in password.lower()
    for marker in ("password", "development", "replace", "change-me", "fixture")
):
    raise ImproperlyConfigured("Production requires a strong non-default database password")
if any(char in host for host in ALLOWED_HOSTS for char in ("/", "@", " ", ":")) or any(
    host.startswith(".") for host in ALLOWED_HOSTS
):
    raise ImproperlyConfigured(
        "Production hosts must be exact hostnames, without ports or wildcards"
    )
private_root = Path(required("INGESTION_STORAGE_ROOT"))
if not private_root.is_absolute() or private_root.resolve().is_relative_to(STATIC_ROOT.resolve()):
    raise ImproperlyConfigured(
        "Production private storage must use an absolute path outside static files"
    )
TRUSTED_PROXY_CIDRS = csv("TRUSTED_PROXY_CIDRS")
for cidr in TRUSTED_PROXY_CIDRS:
    try:
        network = ipaddress.ip_network(cidr)
        if network.prefixlen == 0:
            raise ValueError()
    except ValueError:
        raise ImproperlyConfigured(
            "Trusted proxy CIDRs must be explicit restricted networks"
        ) from None
READINESS_PRIVATE_STORAGE = True
if (
    os.environ.get("BILLING_PROVIDER", "disabled") != "disabled"
    or os.environ.get("BILLING_SIMULATOR_ENABLED", "false").lower() != "false"
):
    raise ImproperlyConfigured(
        "Payment collection is unconfigured; production simulators are prohibited"
    )
READINESS_DATABASE_ROLE = True
if os.environ.get("INTEGRATION_TEST_TRANSPORT", "false").lower() != "false":
    raise ImproperlyConfigured("Production integration test transports are prohibited")
INTEGRATION_OUTBOUND_ENABLED = os.environ.get("INTEGRATION_OUTBOUND_ENABLED", "false") == "true"
INTEGRATION_ALLOWED_HOSTS = csv("INTEGRATION_ALLOWED_HOSTS")
INTEGRATION_SIGNING_CURRENT = os.environ.get("INTEGRATION_SIGNING_CURRENT", "v1")
try:
    INTEGRATION_SIGNING_KEYS = json.loads(os.environ.get("INTEGRATION_SIGNING_KEYS", "{}"))
    if not isinstance(INTEGRATION_SIGNING_KEYS, dict) or any(
        not isinstance(k, str)
        or not isinstance(v, str)
        or not 32 <= len(base64.b64decode(v, validate=True)) <= 64
        or base64.b64decode(v, validate=True).startswith(b"synthetic-")
        for k, v in INTEGRATION_SIGNING_KEYS.items()
    ):
        raise ValueError()
    if len(INTEGRATION_SIGNING_KEYS) > 3 or any(
        not key.isalnum() for key in INTEGRATION_SIGNING_KEYS
    ):
        raise ValueError()
    if INTEGRATION_OUTBOUND_ENABLED and (
        not INTEGRATION_ALLOWED_HOSTS or INTEGRATION_SIGNING_CURRENT not in INTEGRATION_SIGNING_KEYS
    ):
        raise ValueError()
except (ValueError, TypeError):
    raise ImproperlyConfigured(
        "Outbound integrations require dedicated valid signing configuration and approved hosts"
    ) from None
INGESTION_ALLOW_UNSCANNED = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
# Subdomain HSTS and preload require explicit control of every subdomain; deferred.
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.environ.get("DJANGO_HSTS_INCLUDE_SUBDOMAINS", "false") == "true"
SECURE_HSTS_PRELOAD = os.environ.get("DJANGO_HSTS_PRELOAD", "false") == "true"
SECURE_REFERRER_POLICY = "same-origin"
if os.environ.get("DJANGO_TRUST_PROXY") == "true":
    if not TRUSTED_PROXY_CIDRS:
        raise ImproperlyConfigured(
            "Proxy trust requires restricted peer CIDRs and ingress header stripping"
        )
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
