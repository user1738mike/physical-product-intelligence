import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from products.models import Snapshot

SCOPES = ("catalog:read", "assessments:read", "assessments:export")


class PlanPolicy(Snapshot):
    plan = models.OneToOneField("commercial.Plan", on_delete=models.PROTECT)
    credentials_limit = models.PositiveSmallIntegerField(default=3)
    destinations_limit = models.PositiveSmallIntegerField(default=2)
    api_enabled = models.BooleanField(default=False)
    webhooks_enabled = models.BooleanField(default=False)


class Credential(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    issuer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    name = models.CharField(max_length=80)
    verifier = models.CharField(max_length=64)
    scopes = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True)
    last_used_at = models.DateTimeField(null=True)


class Admission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    credential = models.ForeignKey(Credential, on_delete=models.PROTECT)
    expires_at = models.DateTimeField(db_index=True)


class Destination(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    issuer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    url = models.CharField(max_length=500)
    revision = models.PositiveIntegerField(default=1)
    enabled = models.BooleanField(default=True)
    subscriptions = models.JSONField(default=list)
    key_version = models.PositiveIntegerField(default=1)
    previous_key_version = models.PositiveIntegerField(null=True)
    overlap_until = models.DateTimeField(null=True)
    root_version = models.CharField(max_length=24)
    created_at = models.DateTimeField(default=timezone.now)


class Event(Snapshot):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    assessment = models.OneToOneField("compatibility.Assessment", on_delete=models.PROTECT)
    kind = models.CharField(max_length=40, default="assessment.completed")
    body = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)


class Delivery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.PROTECT)
    destination = models.ForeignKey(Destination, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField()
    state = models.CharField(max_length=12, default="pending")
    attempts = models.PositiveSmallIntegerField(default=0)
    due_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField()
    lease = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    diagnostic = models.CharField(max_length=32, blank=True)
    status_code = models.PositiveSmallIntegerField(null=True)
    replays = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "destination"], name="integration_event_destination"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    state__in=["pending", "claimed", "delivered", "retryable", "terminal", "paused"]
                ),
                name="integration_delivery_state",
            ),
        ]


class DeliveryAttempt(Snapshot):
    delivery = models.ForeignKey(Delivery, on_delete=models.PROTECT)
    lease = models.UUIDField()
    state = models.CharField(max_length=12)
    diagnostic = models.CharField(max_length=32)
    status_code = models.PositiveSmallIntegerField(null=True)
    created_at = models.DateTimeField(default=timezone.now)
