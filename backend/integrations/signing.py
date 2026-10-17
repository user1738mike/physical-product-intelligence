"""Standard Webhooks 1.0 symmetric signatures. No payload reserialization during verification."""

import base64
import hmac
import time

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def endpoint_key(destination, version=None):
    roots = settings.INTEGRATION_SIGNING_KEYS
    try:
        root = base64.b64decode(roots[destination.root_version], validate=True)
        if len(root) < 32:
            raise ValueError()
    except (KeyError, ValueError):
        raise ImproperlyConfigured("Outbound signing material is unavailable.") from None
    context = f"ppi-webhooks-v1:{destination.pk}:{version or destination.key_version}".encode()
    return "whsec_" + base64.b64encode(hmac.digest(root, context, "sha256")).decode()


def signature(secret, event_id, timestamp, body):
    key = base64.b64decode(secret.removeprefix("whsec_"), validate=True)
    message = str(event_id).encode() + b"." + str(timestamp).encode() + b"." + body
    return "v1," + base64.b64encode(hmac.digest(key, message, "sha256")).decode()


def headers(destination, event, now):
    timestamp = str(int(now.timestamp()))
    values = [signature(endpoint_key(destination), event.pk, timestamp, event.body.encode())]
    if destination.previous_key_version and destination.overlap_until > now:
        values.append(
            signature(
                endpoint_key(destination, destination.previous_key_version),
                event.pk,
                timestamp,
                event.body.encode(),
            )
        )
    return {
        "webhook-id": str(event.pk),
        "webhook-timestamp": timestamp,
        "webhook-signature": " ".join(values),
        "Content-Type": "application/json",
    }


def verify(secret, event_id, timestamp, body, value, *, now=None):
    if (
        not str(timestamp).isdigit()
        or "." in str(event_id)
        or abs((time.time() if now is None else now) - int(timestamp)) > 300
    ):
        return False
    try:
        expected = signature(secret, event_id, timestamp, body)
        return any(hmac.compare_digest(expected, part) for part in value.split(" ")[:4])
    except (ValueError, TypeError):
        return False
