import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Recommendation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recommendations"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    tracks = models.JSONField(default=list, blank=True)
    seed_params = models.JSONField(default=dict, blank=True)
    source = models.CharField(max_length=40, default="search_v1")
    error = models.TextField(null=True, blank=True)
    task_id = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="rec_user_created_idx"),
            models.Index(fields=["status"], name="rec_status_idx"),
        ]

    def __str__(self) -> str:
        return f"Recommendation<{self.user_id} {self.status} {len(self.tracks)} tracks>"

    def mark_ready(self, tracks, seed_params, source="search_v1"):
        self.tracks = tracks
        self.seed_params = seed_params
        self.source = source
        self.status = self.Status.READY
        self.error = None
        self.completed_at = timezone.now()
        self.save(
            update_fields=["tracks", "seed_params", "source", "status", "error", "completed_at"]
        )

    def mark_failed(self, error: str):
        self.status = self.Status.FAILED
        self.error = error[:2000]
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "error", "completed_at"])


class SpotifyCacheQuerySet(models.QuerySet):
    def expired(self):
        return self.filter(expires_at__lte=timezone.now())

    def live(self):
        return self.filter(expires_at__gt=timezone.now())


class SpotifyCache(models.Model):
    """Persistent copy of raw Spotify responses keyed by endpoint + params."""

    cache_key = models.CharField(max_length=64, unique=True)
    endpoint = models.CharField(max_length=64)
    params = models.JSONField(default=dict)
    response = models.JSONField()
    fetched_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    objects = SpotifyCacheQuerySet.as_manager()

    class Meta:
        indexes = [models.Index(fields=["expires_at"], name="spotifycache_expires_idx")]

    def __str__(self) -> str:
        return f"SpotifyCache<{self.endpoint} {self.cache_key[:8]}>"

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()
