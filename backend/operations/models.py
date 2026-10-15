from django.db import models


class RateBucket(models.Model):
    """Opaque shared fixed-window counters; no request bodies, credentials or raw IPs."""

    key = models.CharField(max_length=64, primary_key=True)
    window_start = models.BigIntegerField()
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
