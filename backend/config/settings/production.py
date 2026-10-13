import os
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
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
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
# Subdomain HSTS and preload require explicit control of every subdomain; deferred.
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_REFERRER_POLICY = "same-origin"
if os.environ.get("DJANGO_TRUST_PROXY") == "true":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
