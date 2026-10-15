import json
import logging
import math
import re
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": re.sub(r"[^A-Za-z0-9_.]", "_", record.name)[:80],
            # Avoid exception messages containing database credentials or input values.
            "event": "application_error"
            if record.exc_info
            else record.getMessage()
            if record.getMessage()
            in {
                "http_request",
                "database_unavailable",
                "readiness_unavailable",
                "rate_limited",
                "limiter_unavailable",
                "audit_event",
            }
            else "application_event",
        }
        if record.name in ("django.server", "django.request") or record.name.startswith(
            "django.security"
        ):
            # Framework request messages can include untrusted query strings.
            payload["event"] = "framework_http_error" if record.levelno >= 40 else "framework_http"
        for field in (
            "request_id",
            "method",
            "path",
            "status",
            "duration_ms",
            "action",
            "outcome",
            "scope",
        ):
            if hasattr(record, field):
                value = getattr(record, field)
                if isinstance(value, (int, float)):
                    if math.isfinite(value):
                        payload[field] = value
                elif (
                    isinstance(value, str)
                    and len(value) <= 200
                    and not any(ord(char) < 32 for char in value)
                ):
                    payload[field] = value
        return json.dumps(payload)
