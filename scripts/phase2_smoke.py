"""Exercise loopback frontend session/CSRF proxy; creates disposable test accounts/tenants."""

import argparse
import json
import secrets
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

ORIGIN = "http://127.0.0.1:3000"


class Browser:
    def __init__(self):
        self.cookies = CookieJar()
        self.http = build_opener(HTTPCookieProcessor(self.cookies))

    def request(self, path, *, data=None, expected=200, method=None, csrf=True, origin=ORIGIN):
        method = method or ("GET" if data is None else "POST")
        headers = {"Origin": origin, "Accept": "application/json"}
        if method not in {"GET", "HEAD", "OPTIONS"} and csrf:
            token = self.request("/api/v1/auth/csrf/")["csrfToken"]
            headers["X-CSRFToken"] = token
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(
            ORIGIN + path,
            data=None if data is None else json.dumps(data).encode(),
            headers=headers,
            method=method,
        )
        try:
            response = self.http.open(request, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            assert response.status == expected, (
                f"{path}: expected {expected}, received {response.status}"
            )
            assert "no-store" in response.headers.get("Cache-Control", ""), path
            payload = response.read()
            if not payload:
                return None
            if "application/json" in response.headers.get("Content-Type", ""):
                return json.loads(payload)
            assert expected >= 400, f"{path}: unexpected non-JSON success"
            return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--read-cycles",
        type=int,
        default=50,
        help="Consecutive CSRF/profile read pairs per account (default: 50).",
    )
    parser.add_argument(
        "--allow-create-test-data",
        action="store_true",
        required=True,
        help="Use only with a disposable test database; creates accounts and tenants.",
    )
    args = parser.parse_args()
    if args.read_cycles < 1:
        parser.error("--read-cycles must be positive")
    users = []
    for _ in range(2):
        browser = Browser()
        username = "smoke-" + secrets.token_hex(8)
        credentials = {"username": username, "password": secrets.token_hex(24)}
        browser.request("/api/v1/auth/login/", data=credentials, csrf=False, expected=403)
        browser.request("/api/v1/auth/register/", data=credentials, csrf=False, expected=403)
        profile = browser.request("/api/v1/auth/register/", data=credentials, expected=201)
        authenticated = browser.request("/api/v1/auth/login/", data=credentials)
        assert profile == authenticated == browser.request("/api/v1/auth/me/")
        cookies = {cookie.name: cookie for cookie in browser.cookies}
        session = cookies["sessionid"]
        assert session.has_nonstandard_attr("HttpOnly")
        assert session.get_nonstandard_attr("SameSite") == "Lax"
        assert session.discard, "Session must expire on browser close"
        assert cookies["csrftoken"].get_nonstandard_attr("SameSite") == "Lax"
        browser.request("/api/v1/auth/logout/", data={}, csrf=False, expected=403)
        browser.request(
            "/api/v1/auth/logout/", data={}, origin="https://evil.example", expected=403
        )
        assert profile == browser.request("/api/v1/auth/me/")
        # Catch pooled proxy socket failures between consecutive authenticated reads.
        for _ in range(args.read_cycles):
            browser.request("/api/v1/auth/csrf/")
            assert profile == browser.request("/api/v1/auth/me/")
        organization = browser.request(
            "/api/v1/organizations/",
            data={"name": "Disposable smoke tenant", "slug": username},
            expected=201,
        )
        memberships = browser.request("/api/v1/auth/memberships/")["results"]
        assert len(memberships) == 1 and memberships[0]["role"] == "owner"
        users.append((browser, organization, memberships[0]))
    first, own, _ = users[0]
    _, other, other_membership = users[1]
    first.request(f"/api/v1/organizations/{other['id']}/", expected=404)
    first.request(
        f"/api/v1/organizations/{own['id']}/members/{other_membership['id']}/",
        expected=404,
    )
    first.request(
        f"/api/v1/organizations/{other['id']}/members/",
        data={"username": "missing"},
        expected=404,
    )
    events = first.request(f"/api/v1/organizations/{own['id']}/audit/")["results"]
    assert any(event["action"] == "organization.created" for event in events)
    # Give the outsider ordinary membership, then exercise member/admin boundaries.
    second = users[1][0]
    member = first.request(
        f"/api/v1/organizations/{own['id']}/members/",
        data={"username": other_membership["user"]["username"]},
        expected=201,
    )
    tenant = f"/api/v1/organizations/{own['id']}/"
    second.request(tenant)
    second.request(tenant, method="PATCH", data={"name": "Forbidden"}, expected=403)
    second.request(tenant + "audit/", expected=403)
    member_path = tenant + f"members/{member['id']}/"
    second.request(member_path, method="PATCH", data={"role": "admin"}, expected=403)
    first.request(member_path, method="PATCH", data={"role": "admin"})
    second.request(tenant, method="PATCH", data={"name": "Admin permitted"})
    second.request(tenant + "state/", data={"is_active": False}, expected=403)
    second.request(member_path, method="PATCH", data={"role": "member"}, expected=403)
    first.request(member_path, method="DELETE", expected=204)
    second.request(tenant, expected=404)
    old_session = next(cookie.value for cookie in first.cookies if cookie.name == "sessionid")
    first.request("/api/v1/auth/logout/", data={}, expected=204)
    first.request("/api/v1/auth/me/", expected=403)
    replay = Browser()
    replay.http.addheaders = [("Cookie", f"sessionid={old_session}")]
    replay.request("/api/v1/auth/me/", expected=403)
    print(
        "PASS real frontend proxy: CSRF/origin denial, cookies, registration, login, "
        f"{args.read_cycles * 4} repeated reads, tenant/role denial, revocation, audit, "
        "logout and session replay denial"
    )


if __name__ == "__main__":
    main()
