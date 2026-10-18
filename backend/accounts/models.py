import uuid

from django.conf import settings
from django.db import models


class RecoveryGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recovery_grants"
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="issued_recoveries"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verifier = models.CharField(max_length=64)
    password_fingerprint = models.CharField(max_length=64)
    case_reference = models.CharField(max_length=120)
    consumed_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)
