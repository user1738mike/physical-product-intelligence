"""Standard Webhooks receiver example. Defaults to an in-memory, offline self-test."""

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def verify(secret, event_id, timestamp, body, signatures, *, now=None):
    try:
        if (
            not timestamp.isdigit()
            or not event_id
            or "." in event_id
            or abs((time.time() if now is None else now) - int(timestamp)) > 300
        ):
            return False
        key = base64.b64decode(secret.removeprefix("whsec_"), validate=True)
        digest = hmac.digest(
            key, event_id.encode() + b"." + timestamp.encode() + b"." + body, "sha256"
        )
        expected = "v1," + base64.b64encode(digest).decode()
        return any(hmac.compare_digest(expected, part) for part in signatures.split(" ")[:4])
    except (ValueError, TypeError):
        return False


class Consumer:
    def __init__(self, database=":memory:"):
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS received "
            "(event_id TEXT PRIMARY KEY, body_sha256 TEXT NOT NULL)"
        )

    def accept(self, secret, event_id, timestamp, body, signatures):
        if not verify(secret, event_id, timestamp, body, signatures):
            return "invalid"
        data = json.loads(body)
        if (
            data.get("id") != event_id
            or data.get("schema_version") != "1"
            or data.get("type") != "assessment.completed"
        ):
            return "invalid"
        digest = hashlib.sha256(body).hexdigest()
        with self.lock, self.db:
            prior = self.db.execute(
                "SELECT body_sha256 FROM received WHERE event_id=?", [event_id]
            ).fetchone()
            if prior:
                return "duplicate" if prior[0] == digest else "conflict"
            self.db.execute("INSERT INTO received VALUES (?,?)", [event_id, digest])
            # Commit business effects here, or enqueue an idempotent local job.
        return "accepted"


def self_test():
    secret = "whsec_" + base64.b64encode(secrets.token_bytes(32)).decode()
    event_id, timestamp = "synthetic-event", str(int(time.time()))
    body = json.dumps(
        {
            "schema_version": "1",
            "id": event_id,
            "type": "assessment.completed",
            "data": {"assessment_id": "synthetic-id"},
        },
        separators=(",", ":"),
    ).encode()
    signature = (
        "v1,"
        + base64.b64encode(
            hmac.digest(
                base64.b64decode(secret[6:]),
                event_id.encode() + b"." + timestamp.encode() + b"." + body,
                "sha256",
            )
        ).decode()
    )
    consumer = Consumer()
    assert consumer.accept(secret, event_id, timestamp, body, signature) == "accepted"
    assert consumer.accept(secret, event_id, timestamp, body, signature) == "duplicate"
    assert not verify(secret, event_id, timestamp, body + b" ", signature)
    consumer.db.close()
    return {"status": "passed", "verified": True, "deduplicated": True, "external_requests": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--database", default=":memory:")
    args = parser.parse_args()
    if not args.serve:
        print(json.dumps(self_test()))
        return
    secret = os.environ.get("WAREHOUSE_WEBHOOK_SECRET")
    if not secret:
        parser.error("Set WAREHOUSE_WEBHOOK_SECRET using your secure local configuration.")
    consumer = Consumer(args.database)

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192:
                    raise ValueError()
                self.connection.settimeout(5)
                body = self.rfile.read(size)
                result = consumer.accept(
                    secret,
                    self.headers.get("webhook-id", ""),
                    self.headers.get("webhook-timestamp", ""),
                    body,
                    self.headers.get("webhook-signature", ""),
                )
                self.send_response(204 if result in {"accepted", "duplicate"} else 400)
                self.send_header("Content-Length", "0")
                self.end_headers()
            except (ValueError, OSError):
                self.send_error(400)

        def log_message(self, *args):
            pass

    # Loopback demonstration only. Real ingestion needs a hardened HTTPS frontend and shared DB.
    with ThreadingHTTPServer(("127.0.0.1", args.port), Receiver) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
