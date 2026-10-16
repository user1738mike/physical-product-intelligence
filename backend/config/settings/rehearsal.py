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
AI_EXTRACTION_ENABLED = True
AI_EXTRACTION_PROVIDER = "recorded"
AI_EXTRACTION_MODEL = "recorded-spec-v1"
