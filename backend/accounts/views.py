from django.contrib.auth import authenticate, get_user_model, login, logout
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from audit.services import record

from .serializers import (
    CredentialsSerializer,
    CsrfSerializer,
    DetailSerializer,
    ProfileSerializer,
    RegistrationSerializer,
)


@method_decorator(never_cache, name="dispatch")
class PrivateResponseView(APIView):
    """Never cache identity or tenant data, including permission failures."""

    def handle_exception(self, exc):
        # Tenant transactions have exited/rolled back before this failure event is saved.
        if isinstance(exc, (NotFound, PermissionDenied)) and self.request.user.is_authenticated:
            record("authorization.denied", actor=self.request.user, outcome="failure")
        return super().handle_exception(exc)


class CsrfView(PrivateResponseView):
    permission_classes = [AllowAny]

    @extend_schema(responses=CsrfSerializer)
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class RegisterView(PrivateResponseView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    @extend_schema(
        request=RegistrationSerializer, responses={201: ProfileSerializer, 400: DetailSerializer}
    )
    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(**serializer.validated_data)
                record("account.created", actor=user)
        except IntegrityError:
            return Response({"detail": "Account could not be created."}, status=400)
        return Response(ProfileSerializer(user).data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(PrivateResponseView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        request=CredentialsSerializer, responses={200: ProfileSerializer, 400: DetailSerializer}
    )
    def post(self, request):
        serializer = CredentialsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request=request, **serializer.validated_data)
        if user is None:
            record("login.failed", outcome="failure")
            return Response({"detail": "Invalid credentials."}, status=400)
        with transaction.atomic():
            login(request, user)
            record("login.succeeded", actor=user)
        return Response(ProfileSerializer(user).data)


class LogoutView(PrivateResponseView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        with transaction.atomic():
            record("logout.succeeded", actor=request.user)
            logout(request)
        return Response(status=204)


class MeView(PrivateResponseView):
    @extend_schema(responses=ProfileSerializer)
    def get(self, request):
        return Response(ProfileSerializer(request.user).data)
