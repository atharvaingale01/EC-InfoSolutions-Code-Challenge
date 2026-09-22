"""Response-shape serializers; used for OpenAPI docs and output typing."""

from rest_framework import serializers


class ByActionSerializer(serializers.Serializer):
    play = serializers.IntegerField()
    like = serializers.IntegerField()
    skip = serializers.IntegerField()


class ActivityStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    by_action = ByActionSerializer()
    like_rate = serializers.FloatField()
    skip_rate = serializers.FloatField()


class SummarySerializer(serializers.Serializer):
    class SummaryUsers(serializers.Serializer):
        total = serializers.IntegerField()
        active_7d = serializers.IntegerField()

    class SummaryRecommendations(serializers.Serializer):
        total_generated = serializers.IntegerField()
        ready = serializers.IntegerField()
        failed = serializers.IntegerField()
        pending = serializers.IntegerField()
        avg_tracks = serializers.FloatField()

    class SummaryCache(serializers.Serializer):
        spotify_cache_entries = serializers.IntegerField()

    users = SummaryUsers()
    activity = ActivityStatsSerializer()
    recommendations = SummaryRecommendations()
    cache = SummaryCache()
    generated_at = serializers.DateTimeField()


class TrendsSerializer(serializers.Serializer):
    class TrendGenre(serializers.Serializer):
        genre = serializers.CharField()
        users = serializers.IntegerField()

    class TrendArtist(serializers.Serializer):
        artist_name = serializers.CharField()
        interactions = serializers.IntegerField()
        likes = serializers.IntegerField()
        plays = serializers.IntegerField()

    class TrendTrack(serializers.Serializer):
        track_id = serializers.CharField()
        track_name = serializers.CharField()
        artist_name = serializers.CharField()
        plays = serializers.IntegerField()
        likes = serializers.IntegerField()
        skips = serializers.IntegerField()
        interactions = serializers.IntegerField()

    window_days = serializers.IntegerField()
    top_genres = TrendGenre(many=True)
    top_artists = TrendArtist(many=True)
    top_tracks = TrendTrack(many=True)


class UserSummarySerializer(serializers.Serializer):
    class UserTopArtist(serializers.Serializer):
        artist_name = serializers.CharField()
        interactions = serializers.IntegerField()

    class UserRecommendations(serializers.Serializer):
        generated = serializers.IntegerField()
        last_generated_at = serializers.DateTimeField(allow_null=True)
        tracks_recommended = serializers.IntegerField()

    user_id = serializers.UUIDField()
    activity = ActivityStatsSerializer()
    top_artists = UserTopArtist(many=True)
    recommendations = UserRecommendations()
    engagement_rate = serializers.FloatField()
    last_active_at = serializers.DateTimeField(allow_null=True)
