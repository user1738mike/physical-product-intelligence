import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            # Avoid exception messages containing database credentials or input values.
            "event": "application_error" if record.exc_info else record.getMessage(),
        }
        if record.name in ("django.server", "django.request") or record.name.startswith(
            "django.security"
        ):
            # Framework request messages can include untrusted query strings.
            payload["event"] = "framework_http_error" if record.levelno >= 40 else "framework_http"
        for field in ("request_id", "method", "path", "status", "duration_ms"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload)
