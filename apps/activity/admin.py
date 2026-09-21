from django.contrib import admin

from .models import UserActivity


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ["user", "action", "track_name", "artist_name", "created_at"]
    list_filter = ["action"]
    search_fields = ["user__email", "track_name", "artist_name", "track_id"]
    readonly_fields = ["created_at"]
