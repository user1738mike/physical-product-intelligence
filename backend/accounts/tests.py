import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from audit.models import AuditEvent

PASSWORD = "fixture-only!LongPass42"


class AuthenticationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="alice", password=PASSWORD)
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf(self):
        response = self.client.get("/api/v1/auth/csrf/")
        self.assertIn("no-store", response["Cache-Control"])
        return response.json()["csrfToken"]

    def login(self, **credentials):
        return self.client.post(
            "/api/v1/auth/login/",
            credentials or {"username": "alice", "password": PASSWORD},
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf(),
        )

    def test_anonymous_identity_and_tenant_requests_denied(self):
        for url in ("/api/v1/auth/me/", "/api/v1/auth/memberships/", "/api/v1/organizations/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)
            self.assertNotIn("alice", response.content.decode())

    def test_login_registration_and_logout_require_csrf(self):
        for endpoint in ("login", "register"):
            response = self.client.post(
                f"/api/v1/auth/{endpoint}/",
                {"username": "newperson", "password": PASSWORD},
                format="json",
            )
            self.assertEqual(response.status_code, 403)
        self.assertFalse(get_user_model().objects.filter(username="newperson").exists())
        self.assertEqual(self.login().status_code, 200)
        response = self.client.post("/api/v1/auth/logout/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)

    def test_login_rotates_session_and_logout_invalidates_old_cookie(self):
        anonymous = self.client.session
        anonymous["prelogin"] = "fixture"
        anonymous.save()
        anonymous_key = anonymous.session_key
        self.assertEqual(self.login().status_code, 200)
        old_session = self.client.cookies["sessionid"].value
        self.assertNotEqual(old_session, anonymous_key)
        self.assertEqual(self.login().status_code, 200)
        current_session = self.client.cookies["sessionid"].value
        # Re-login as the same account need not rotate an already authenticated session.
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.json(), {"id": self.user.pk, "username": "alice"})
        self.assertIn("no-store", response["Cache-Control"])
        response = self.client.post("/api/v1/auth/logout/", HTTP_X_CSRFTOKEN=self.csrf())
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 403)
        for cookie in {old_session, current_session}:
            replay = APIClient()
            replay.cookies["sessionid"] = cookie
            self.assertEqual(replay.get("/api/v1/auth/me/").status_code, 403)
        self.assertTrue(
            AuditEvent.objects.filter(action="logout.succeeded", actor=self.user).exists()
        )

    def test_invalid_and_inactive_credentials_are_generic_and_audited(self):
        responses = [
            self.login(username="missing", password=PASSWORD),
            self.login(username="alice", password="wrong"),
        ]
        self.user.is_active = False
        self.user.save()
        responses.append(self.login())
        for response in responses:
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), {"detail": "Invalid credentials."})
        events = AuditEvent.objects.filter(action="login.failed")
        self.assertEqual(events.count(), 3)
        for event in events:
            self.assertIsNone(event.actor_id)
            self.assertEqual(event.metadata, {})
            self.assertNotIn(PASSWORD, json.dumps(event.metadata))

    def test_existing_django_usernames_can_login_without_changing_registration_policy(self):
        for username in ("legacy+person@example.com", "旧用户"):
            user = get_user_model().objects.create_user(username=username, password=PASSWORD)
            response = self.login(username=username, password=PASSWORD)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"id": user.pk, "username": username})
            rejected = self.client.post(
                "/api/v1/auth/register/",
                {"username": username, "password": PASSWORD},
                format="json",
                HTTP_X_CSRFTOKEN=self.csrf(),
            )
            self.assertEqual(rejected.status_code, 400)

    def test_account_deactivation_and_password_change_revoke_authentication(self):
        self.login()
        self.user.set_password("different-fixture-password")
        self.user.save()
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 403)
        self.user.set_password(PASSWORD)
        self.user.save()
        self.login()
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 403)

    def test_registration_never_trusts_privileges_and_validates_password(self):
        base = {"username": "newperson", "password": PASSWORD}
        for field in ("is_staff", "is_superuser", "is_active", "role", "id"):
            response = self.client.post(
                "/api/v1/auth/register/",
                {**base, field: True},
                format="json",
                HTTP_X_CSRFTOKEN=self.csrf(),
            )
            self.assertEqual(response.status_code, 400)
        cache.clear()
        response = self.client.post(
            "/api/v1/auth/register/",
            {**base, "password": "123"},
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(get_user_model().objects.filter(username="newperson").exists())
        response = self.client.post(
            "/api/v1/auth/register/", base, format="json", HTTP_X_CSRFTOKEN=self.csrf()
        )
        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get(username="newperson")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertNotIn("password", response.json())
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 403)
        duplicate = self.client.post(
            "/api/v1/auth/register/", base, format="json", HTTP_X_CSRFTOKEN=self.csrf()
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(get_user_model().objects.filter(username="newperson").count(), 1)

    def test_login_throttle_limits_failed_attempts(self):
        for _ in range(10):
            self.assertEqual(self.login(username="missing", password="wrong").status_code, 400)
        self.assertEqual(self.login(username="missing", password="wrong").status_code, 429)

    def test_hostile_csrf_origin_and_missing_tenant_csrf_rejected(self):
        token = self.csrf()
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "alice", "password": PASSWORD},
            format="json",
            HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN="https://evil.example",
        )
        self.assertEqual(response.status_code, 403)
        self.login()
        response = self.client.post(
            "/api/v1/organizations/", {"name": "Safe", "slug": "safe"}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_session_cookie_policy_and_absolute_expiry(self):
        self.login()
        cookie = self.client.cookies["sessionid"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        from django.contrib.sessions.models import Session
        from django.utils import timezone

        Session.objects.filter(session_key=cookie.value).update(expire_date=timezone.now())
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 403)

    def test_login_rotates_csrf_secret_and_rejects_the_prelogin_token(self):
        old_token = self.csrf()
        old_secret = self.client.cookies["csrftoken"].value
        self.assertEqual(self.login().status_code, 200)
        self.assertNotEqual(self.client.cookies["csrftoken"].value, old_secret)
        response = self.client.post(
            "/api/v1/organizations/",
            {"name": "Rotation check", "slug": "rotation-check"},
            format="json",
            HTTP_X_CSRFTOKEN=old_token,
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            "/api/v1/organizations/",
            {"name": "Rotation check", "slug": "rotation-check"},
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf(),
        )
        self.assertEqual(response.status_code, 201)

    @override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
    def test_https_authentication_sets_secure_cookies(self):
        token = self.client.get("/api/v1/auth/csrf/", secure=True).json()["csrfToken"]
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "alice", "password": PASSWORD},
            format="json",
            secure=True,
            HTTP_ORIGIN="https://testserver",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        for name in ("sessionid", "csrftoken"):
            self.assertTrue(response.cookies[name]["secure"])
            self.assertEqual(response.cookies[name]["samesite"], "Lax")
        self.assertTrue(response.cookies["sessionid"]["httponly"])

    def test_registration_throttle_and_non_object_payloads_fail_safely(self):
        token = self.csrf()
        for _ in range(5):
            response = self.client.post(
                "/api/v1/auth/register/", [], format="json", HTTP_X_CSRFTOKEN=token
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/register/", [], format="json", HTTP_X_CSRFTOKEN=token
            ).status_code,
            429,
        )
