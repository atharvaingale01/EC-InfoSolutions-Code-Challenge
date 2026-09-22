from rest_framework import serializers


class TrackSerializer(serializers.Serializer):
    spotify_id = serializers.CharField()
    name = serializers.CharField()
    artists = serializers.ListField(child=serializers.CharField())
    album = serializers.CharField(allow_blank=True)
    preview_url = serializers.URLField(allow_null=True)
    external_url = serializers.URLField(allow_blank=True)
    popularity = serializers.IntegerField()
    duration_ms = serializers.IntegerField()
    seed = serializers.CharField()
    score = serializers.FloatField()


class RecommendationListSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    recommendation_id = serializers.UUIDField()
    generated_at = serializers.DateTimeField(allow_null=True)
    source = serializers.CharField()
    cached = serializers.BooleanField()
    refresh_pending = serializers.BooleanField()
    count = serializers.IntegerField()
    tracks = TrackSerializer(many=True)


class RefreshAcceptedSerializer(serializers.Serializer):
    recommendation_id = serializers.UUIDField()
    task_id = serializers.CharField(allow_null=True)
    status = serializers.CharField()


class RecommendationPendingSerializer(serializers.Serializer):
    status = serializers.CharField()
    recommendation_id = serializers.UUIDField()
