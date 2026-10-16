"""ClamAV INSTREAM adapter; no shell command, source filename, or public document URL."""

import os
import socket
import struct
import time


def scanner_ready():
    """Bounded dependency probe, not a clean-file verdict or signature-freshness claim."""
    host = os.environ.get("CLAMD_HOST", "").strip()
    port = int(os.environ.get("CLAMD_PORT", "3310"))
    if not host or not 1 <= port <= 65535:
        return False
    with socket.create_connection((host, port), timeout=2) as stream:
        stream.settimeout(2)
        stream.sendall(b"zPING\0")
        return stream.recv(32) == b"PONG\0"


def clamd_scan(data):
    host = os.environ.get("CLAMD_HOST", "").strip()
    port = int(os.environ.get("CLAMD_PORT", "3310"))
    if not host or not 1 <= port <= 65535 or len(data) > 2 * 1024**2:
        raise ValueError("Scanner configuration or source bound invalid")
    deadline = time.monotonic() + 5
    with socket.create_connection((host, port), timeout=5) as stream:

        def remaining():
            seconds = deadline - time.monotonic()
            if seconds <= 0:
                raise TimeoutError("Scanner deadline exceeded")
            stream.settimeout(seconds)

        remaining()
        stream.sendall(b"zINSTREAM\0")
        for start in range(0, len(data), 65536):
            remaining()
            chunk = data[start : start + 65536]
            stream.sendall(struct.pack("!I", len(chunk)) + chunk)
        remaining()
        stream.sendall(struct.pack("!I", 0))
        response = bytearray()
        while b"\0" not in response:
            remaining()
            block = stream.recv(256)
            if not block or len(response) + len(block) > 1024:
                raise ValueError("Scanner response invalid")
            response.extend(block)
    # Unknown/error/partial responses never count as clean; signature text is not logged.
    return bytes(response) == b"stream: OK\0"
