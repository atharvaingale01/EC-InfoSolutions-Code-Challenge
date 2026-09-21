from rest_framework import serializers

from .models import UserActivity


class UserActivitySerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.id", read_only=True)

    class Meta:
        model = UserActivity
        fields = ["id", "user_id", "track_id", "track_name", "artist_name", "action", "created_at"]
        read_only_fields = ["id", "user_id", "created_at"]

    def validate_track_id(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("track_id may not be blank.")
        return value

    def create(self, validated_data):
        # The acting user always comes from the auth token, never the body.
        return UserActivity.objects.create(user=self.context["request"].user, **validated_data)
