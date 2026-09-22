import hashlib
import json
import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Application user. Email is the login identifier. Music preferences are
    stored as small JSON lists; they are seeds for Spotify lookups, not
    foreign keys, so free-text is acceptable.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150)

    favorite_genres = models.JSONField(default=list, blank=True)
    favorite_artists = models.JSONField(default=list, blank=True)
    moods = models.JSONField(default=list, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.email

    @property
    def has_preferences(self) -> bool:
        return bool(self.favorite_genres or self.favorite_artists or self.moods)

    @property
    def preferences(self) -> tuple:
        return (list(self.favorite_genres), list(self.favorite_artists), list(self.moods))

    @property
    def preferences_hash(self) -> str:
        payload = json.dumps(self.preferences, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()
