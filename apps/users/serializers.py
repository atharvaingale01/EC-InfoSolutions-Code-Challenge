from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.recommendations.spotify.moods import MOOD_MAP

from .models import User

MAX_LIST_ITEMS = 10


class _PreferenceListField(serializers.ListField):
    child = serializers.CharField(max_length=100, allow_blank=False)

    def __init__(self, *, lowercase=False, **kwargs):
        kwargs.setdefault("max_length", MAX_LIST_ITEMS)
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)
        self.lowercase = lowercase

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        cleaned = []
        for value in values:
            value = value.strip()
            if self.lowercase:
                value = value.lower()
            if value and value not in cleaned:
                cleaned.append(value)
        return cleaned


class MoodListField(_PreferenceListField):
    def __init__(self, **kwargs):
        super().__init__(lowercase=True, **kwargs)

    def to_internal_value(self, data):
        moods = super().to_internal_value(data)
        unknown = [m for m in moods if m not in MOOD_MAP]
        if unknown:
            raise serializers.ValidationError(
                f"Unknown mood(s): {', '.join(unknown)}. Allowed: {', '.join(sorted(MOOD_MAP))}."
            )
        return moods


class ProfileSerializer(serializers.ModelSerializer):
    """Read shape for a user profile; also used for authenticated updates."""

    favorite_genres = _PreferenceListField(lowercase=True)
    favorite_artists = _PreferenceListField()
    moods = MoodListField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "name",
            "favorite_genres",
            "favorite_artists",
            "moods",
            "is_staff",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "email", "is_staff", "created_at", "updated_at"]


class RegisterSerializer(ProfileSerializer):
    """Anonymous create: requires email + password."""

    password = serializers.CharField(
        write_only=True, min_length=8, style={"input_type": "password"}
    )

    class Meta(ProfileSerializer.Meta):
        fields = ProfileSerializer.Meta.fields + ["password"]
        read_only_fields = ["id", "is_staff", "created_at", "updated_at"]

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)
