"""Allowlisted HTTPS, validated all-answer DNS and a pinned socket with verified SNI."""

import concurrent.futures
import http.client
import ipaddress
import re
import socket
import ssl
import threading
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from django.conf import settings
from rest_framework.exceptions import ValidationError

RESOLVER = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="webhook-dns")
DNS_SLOTS = threading.BoundedSemaphore(2)


class TransportFailure(Exception):
    pass


def retry_delay(value, *, now=None):
    if not isinstance(value, str) or len(value) > 128:
        return None
    try:
        seconds = (
            int(value)
            if value.isdigit() and len(value) <= 6
            else int((parsedate_to_datetime(value) - (now or datetime.now(UTC))).total_seconds())
        )
        return min(3600, max(1, seconds))
    except (ValueError, TypeError, OverflowError):
        return None


def url_parts(url):
    if (
        not isinstance(url, str)
        or len(url) > 500
        or any(c.isspace() or ord(c) < 33 for c in url)
        or "\\" in url
        or "%" in url
    ):
        raise ValidationError("Use an approved HTTPS destination.")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or parsed.port not in (None, 443)
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host)
            or ".." in host
            or parsed.netloc != host + (":443" if parsed.port else "")
        ):
            raise ValueError()
        if host not in settings.INTEGRATION_ALLOWED_HOSTS:
            raise ValueError()
        return host, parsed.path or "/", parsed.query
    except ValueError:
        raise ValidationError("Use an approved HTTPS destination.") from None


def resolve(host):
    if not DNS_SLOTS.acquire(blocking=False):
        raise TransportFailure("resolver_busy")

    def lookup():
        try:
            return socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        finally:
            DNS_SLOTS.release()

    try:
        future = RESOLVER.submit(lookup)
        answers = future.result(timeout=2)
        addresses = list({item[4][0] for item in answers})
        if (
            not addresses
            or len(addresses) > 16
            or any(not public_address(value) for value in addresses)
        ):
            raise ValueError()
        return addresses
    except (OSError, ValueError, concurrent.futures.TimeoutError):
        raise TransportFailure("destination_unavailable") from None


def public_address(value):
    address = ipaddress.ip_address(value)
    return (
        address.is_global
        and not address.is_reserved
        and not address.is_multicast
        and not address.is_unspecified
        and not getattr(address, "ipv4_mapped", None)
        and not getattr(address, "sixtofour", None)
        and not getattr(address, "teredo", None)
    )


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, 443, timeout=5, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        address = ipaddress.ip_address(self.address)
        raw = socket.socket(
            socket.AF_INET6 if address.version == 6 else socket.AF_INET, socket.SOCK_STREAM
        )
        raw.settimeout(3)
        try:
            raw.connect((self.address, 443))
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def send(url, body, headers):
    host, path, query = url_parts(url)
    addresses = resolve(host)  # Revalidated on every attempt; all answers must be public.
    connection = PinnedHTTPS(host, addresses[0])
    timer = None
    try:
        connection.connect()
        connected_socket = connection.sock

        def abort():
            try:
                connected_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()

        timer = threading.Timer(10, abort)
        timer.daemon = True
        timer.start()
        connection.request(
            "POST", path + ("?" + query if query else ""), body=body, headers=headers
        )
        response = connection.getresponse()
        if len(response.read(4097)) > 4096:
            raise TransportFailure("response_too_large")
        retry = response.getheader("Retry-After", "")
        return response.status, retry_delay(retry)
    except (OSError, http.client.HTTPException):
        raise TransportFailure("network_outcome_unknown") from None
    finally:
        if timer:
            timer.cancel()
        connection.close()
