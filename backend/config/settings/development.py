import os

from .base import *  # noqa: F403
from .environment import csv, postgres

DEBUG = True
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "local-development-only-do-not-use-in-production")
ALLOWED_HOSTS = csv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,backend")
CSRF_TRUSTED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
DATABASES = {"default": postgres()}
