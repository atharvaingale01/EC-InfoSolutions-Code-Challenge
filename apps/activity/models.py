from django.conf import settings
from django.db import models


class UserActivity(models.Model):
    class Action(models.TextChoices):
        PLAY = "play", "Play"
        LIKE = "like", "Like"
        SKIP = "skip", "Skip"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activities"
    )
    track_id = models.CharField(max_length=64)
    track_name = models.CharField(max_length=255, blank=True)
    artist_name = models.CharField(max_length=255, blank=True)
    action = models.CharField(max_length=10, choices=Action.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "user activities"
        indexes = [
            models.Index(fields=["user", "-created_at"], name="activity_user_created_idx"),
            models.Index(fields=["action", "-created_at"], name="activity_action_created_idx"),
            models.Index(fields=["artist_name"], name="activity_artist_idx"),
            models.Index(fields=["track_id"], name="activity_track_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.action} {self.track_id}"
