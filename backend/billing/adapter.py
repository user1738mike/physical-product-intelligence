"""Executable offline simulator. This is not Stripe/Paddle signature verification or collection."""

import hashlib
import hmac
import json
import os
import re

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import GatewayCall, GatewayObject

TEST_KEY = b"ppi-public-synthetic-test-proof-not-a-provider-secret"


def enabled():
    if not getattr(settings, "BILLING_SIMULATOR_ENABLED", False):
        return False
    database = connection.settings_dict["NAME"]
    return bool(
        (
            getattr(settings, "ALLOW_REHEARSAL_PROVIDER", False)
            and re.fullmatch(r"ppi_rehearsal_[a-f0-9]{10}", database)
        )
        or (
            os.environ.get("DJANGO_SETTINGS_MODULE") == "config.settings.test"
            and str(database).startswith("test_")
        )
    )


def require():
    if not enabled():
        raise ValidationError(
            {"code": "collection_unavailable", "detail": "Payment collection is not available."}
        )


def sign(body, timestamp=None):
    require()
    timestamp = str(timestamp if timestamp is not None else int(timezone.now().timestamp()))
    return timestamp, hmac.new(
        TEST_KEY, timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()


def verify(body, timestamp, proof):
    require()
    if (
        len(body) > 65536
        or not isinstance(timestamp, str)
        or not re.fullmatch(r"[0-9]{1,12}", timestamp)
    ):
        raise ValidationError("Invalid synthetic delivery.")
    if abs(timezone.now().timestamp() - int(timestamp)) > 300:
        raise ValidationError("Synthetic delivery expired.")
    expected = sign(body, timestamp)[1]
    if not isinstance(proof, str) or not hmac.compare_digest(proof, expected):
        raise ValidationError("Invalid synthetic delivery proof.")
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        raise ValidationError("Malformed synthetic delivery.") from None
    keys = {
        "event_id",
        "merchant",
        "mode",
        "customer",
        "object_ref",
        "object_version",
        "kind",
        "effect_id",
        "amount_minor",
        "currency",
        "price_id",
        "period_start",
        "period_end",
        "reverses",
    }
    if (
        not isinstance(data, dict)
        or set(data) != keys
        or any(
            not isinstance(v, str) or len(v) > 120 or (k != "reverses" and not v)
            for k, v in data.items()
            if k not in {"amount_minor", "object_version"}
        )
        or type(data["amount_minor"]) is not int
        or not 0 <= data["amount_minor"] <= 10**15
        or type(data["object_version"]) is not int
        or not 1 <= data["object_version"] <= 2147483647
        or data["mode"] != "test"
    ):
        raise ValidationError("Invalid synthetic event contract.")
    return data


class UnknownOutcome(Exception):
    pass


@transaction.atomic
def create(operation):
    require()
    if operation.mode != "test" or operation.provider != "simulator":
        raise ValidationError("Simulator cannot process this mode/provider.")
    obj, created = GatewayObject.objects.get_or_create(
        operation=operation,
        defaults={
            "external_ref": "sim_" + operation.pk.hex,
            "amount_minor": operation.amount_minor,
            "currency": operation.currency,
        },
    )
    if created:
        GatewayCall.objects.create(operation=operation, action="create")
    return obj.external_ref


def lookup(operation):
    require()
    GatewayCall.objects.create(operation=operation, action="lookup")
    return GatewayObject.objects.filter(operation=operation).first()


def payload(
    operation,
    obj,
    *,
    kind="payment.succeeded",
    event_id=None,
    effect_id=None,
    amount=None,
    reverses="",
):
    statement, account = operation.statement, operation.statement.account
    return {
        "event_id": event_id or "sim-event-" + obj.external_ref + "-" + str(obj.version),
        "merchant": account.merchant,
        "mode": account.mode,
        "customer": account.customer_ref,
        "object_ref": obj.external_ref,
        "object_version": obj.version,
        "kind": kind,
        "effect_id": effect_id or "sim-effect-" + obj.external_ref,
        "amount_minor": obj.amount_minor if amount is None else amount,
        "currency": obj.currency,
        "price_id": str(statement.price_id),
        "period_start": statement.period_start.isoformat(),
        "period_end": statement.period_end.isoformat(),
        "reverses": reverses,
    }
