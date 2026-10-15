import ipaddress
import logging
import time
from datetime import UTC, datetime

from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.utils.crypto import salted_hmac
from rest_framework.exceptions import APIException
from rest_framework.settings import api_settings
from rest_framework.throttling import BaseThrottle

logger = logging.getLogger("operations.limits")


class LimiterUnavailable(APIException):
    status_code = 503
    default_detail = "Request admission is temporarily unavailable."
    default_code = "admission_unavailable"


class Limited(Exception):
    pass


def peer_identity(request):
    peer = request.META.get("REMOTE_ADDR", "unknown")
    try:
        address = ipaddress.ip_address(peer)
        trusted = any(address in ipaddress.ip_network(net) for net in settings.TRUSTED_PROXY_CIDRS)
        supplied = request.META.get("HTTP_X_REAL_IP", "")
        if trusted and supplied:
            return str(ipaddress.ip_address(supplied))
    except ValueError:
        pass
    return peer


def consume(keys, limit, duration, now):
    window = int(now) // duration
    expiry = datetime.fromtimestamp((window + 1) * duration, UTC)
    # PostgreSQL and SQLite both implement this atomic conflict update. No cache get/set race.
    with transaction.atomic():
        for key in sorted(keys):
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO operations_ratebucket (key, window_start, count, expires_at) "
                    "VALUES (%s, %s, 1, %s) ON CONFLICT (key) DO UPDATE SET "
                    "window_start = excluded.window_start, expires_at = excluded.expires_at, "
                    "count = CASE WHEN operations_ratebucket.window_start = excluded.window_start "
                    "THEN operations_ratebucket.count + 1 ELSE 1 END "
                    "WHERE operations_ratebucket.window_start <> excluded.window_start "
                    "OR operations_ratebucket.count < %s RETURNING count",
                    [key, window, expiry, limit],
                )
                if cursor.fetchone() is None:
                    raise Limited()


class SharedRateThrottle(BaseThrottle):
    """Fail-closed, DB-shared admission across API processes using the same database/secret."""

    def allow_request(self, request, view):
        # These scopes protect writes and expensive processing, not bounded paginated reads.
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return True
        scope = getattr(view, "throttle_scope", None)
        rate = api_settings.DEFAULT_THROTTLE_RATES.get(scope)
        if not scope or not rate:
            return True
        quantity, period = rate.split("/")
        limit = int(quantity)
        duration = {"s": 1, "m": 60, "h": 3600, "d": 86400}[period[0]]
        subjects = [
            "peer:" + peer_identity(request)
            if scope in {"login", "register"} or not request.user.is_authenticated
            else "user:" + str(request.user.pk)
        ]
        org_id = getattr(view, "kwargs", {}).get("organization_id")
        if request.user.is_authenticated and org_id:
            from organizations.services import authorize

            org, _ = authorize(request.user, org_id)
            subjects.append("organization:" + str(org.pk))
        keys = [
            salted_hmac("shared-rate-v1", scope + ":" + subject).hexdigest() for subject in subjects
        ]
        now = time.time()
        self.remaining = duration - (now % duration)
        try:
            consume(keys, limit, duration, now)
        except Limited:
            logger.info("rate_limited", extra={"scope": scope, "status": 429})
            return False
        except DatabaseError:
            logger.warning("limiter_unavailable", extra={"scope": scope, "status": 503})
            raise LimiterUnavailable() from None
        return True

    def wait(self):
        return self.remaining
