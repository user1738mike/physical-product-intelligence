"""Production controls with explicit synthetic-only fixture extraction, never OpenAI."""

import os
import re

from django.core.exceptions import ImproperlyConfigured

from .production import *  # noqa: F403
from .production import DATABASES

if os.environ.get("PPI_REHEARSAL_FIXTURES") != "synthetic-only" or not re.fullmatch(
    r"ppi_rehearsal_[a-f0-9]{10}", DATABASES["default"]["NAME"]
):
    raise ImproperlyConfigured("Rehearsal settings require an isolated synthetic database")
ALLOW_REHEARSAL_PROVIDER = True
BILLING_SIMULATOR_ENABLED = True
INTEGRATION_TEST_TRANSPORT = True
INTEGRATION_OUTBOUND_ENABLED = True
INTEGRATION_ALLOWED_HOSTS = ["warehouse.example"]
INTEGRATION_SIGNING_CURRENT = "synthetic-v1"
# Public fixture material, confined to the already-guarded disposable rehearsal settings.
INTEGRATION_SIGNING_KEYS = {"synthetic-v1": "c3ludGhldGljLWludGVncmF0aW9uLXJvb3QtMzJieXRlcyE="}
AI_EXTRACTION_ENABLED = True
AI_EXTRACTION_PROVIDER = "recorded"
AI_EXTRACTION_MODEL = "recorded-spec-v1"
