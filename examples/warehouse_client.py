"""Read-only example. No request occurs unless --origin is explicitly supplied."""

import argparse
import json
import os
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin")
    parser.add_argument("--assessment")
    args = parser.parse_args()
    if not args.origin:
        print("Offline default: configure an approved HTTPS origin and WAREHOUSE_API_CREDENTIAL.")
        return
    parsed = urlsplit(args.origin)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        parser.error("Use an approved HTTPS origin without credentials, query or path.")
    token = os.environ.get("WAREHOUSE_API_CREDENTIAL")
    if not token:
        parser.error(
            "Configure WAREHOUSE_API_CREDENTIAL securely; keep it out of URLs and arguments."
        )
    import uuid

    path = (
        f"assessments/{uuid.UUID(args.assessment)}/export/json/"
        if args.assessment
        else "products/?limit=25"
    )
    request = Request(
        args.origin.rstrip("/") + "/api/v1/integration/" + path,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    with build_opener(NoRedirect()).open(request, timeout=10) as response:
        body = response.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise RuntimeError("Response exceeds the documented bound")
        result = json.loads(body)
    # Customer data is returned to the caller; production consumers should store it privately.
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
