import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

# A pending row is "live" (a build is genuinely queued or running) when either it
# has not started yet and is younger than the queue TTL, or it started recently.
QUEUE_TTL = timedelta(minutes=settings.RECS_REFRESH_INTERVAL_MINUTES)
RUNNING_TOO_LONG = timedelta(minutes=15)


class RecommendationQuerySet(models.QuerySet):
    def live_pending(self):
        now = timezone.now()
        return self.filter(status=Recommendation.Status.PENDING).filter(
            models.Q(started_at__isnull=True, created_at__gte=now - QUEUE_TTL)
            | models.Q(started_at__gte=now - RUNNING_TOO_LONG)
        )

    def lost(self):
        """Pending rows that can no longer be running: task lost or worker killed."""
        now = timezone.now()
        return self.filter(status=Recommendation.Status.PENDING).filter(
            models.Q(started_at__isnull=True, created_at__lt=now - QUEUE_TTL)
            | models.Q(started_at__lt=now - RUNNING_TOO_LONG)
        )


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
    prefs_hash = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = RecommendationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="rec_user_created_idx"),
            models.Index(fields=["status"], name="rec_status_idx"),
        ]

    def __str__(self) -> str:
        return f"Recommendation<{self.user_id} {self.status} {len(self.tracks)} tracks>"

    def mark_started(self, task_id: str | None, prefs_hash: str):
        self.started_at = timezone.now()
        self.task_id = task_id
        self.prefs_hash = prefs_hash
        self.save(update_fields=["started_at", "task_id", "prefs_hash"])

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
