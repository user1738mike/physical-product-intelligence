import uuid

from django.conf import settings
from django.db import models


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Audit events are append-only")

    def delete(self):
        raise ValueError("Audit events are append-only")


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    organization = models.ForeignKey(
        "organizations.Organization", null=True, on_delete=models.PROTECT
    )
    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=32, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    outcome = models.CharField(
        max_length=10, choices=[("success", "Success"), ("failure", "Failure")]
    )
    metadata = models.JSONField(default=dict)
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["-timestamp", "-id"]
        indexes = [models.Index(fields=["organization", "-timestamp"], name="audit_org_time")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Audit events are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit events are append-only")
