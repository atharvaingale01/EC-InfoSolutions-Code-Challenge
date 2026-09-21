from django.contrib import admin

from .models import Recommendation, SpotifyCache


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "status", "track_count", "source", "created_at", "completed_at"]
    list_filter = ["status", "source"]
    search_fields = ["user__email"]
    readonly_fields = ["created_at", "completed_at"]

    @admin.display(description="tracks")
    def track_count(self, obj):
        return len(obj.tracks or [])


@admin.register(SpotifyCache)
class SpotifyCacheAdmin(admin.ModelAdmin):
    list_display = ["endpoint", "cache_key", "fetched_at", "expires_at"]
    list_filter = ["endpoint"]
    readonly_fields = ["cache_key", "fetched_at"]
