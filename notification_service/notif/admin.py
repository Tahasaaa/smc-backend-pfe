from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "severity",
        "source",
        "status",
        "user_email",
        "created_at",
        "is_deleted",
    )
    list_filter = ("severity", "source", "status", "is_deleted", "created_at")
    search_fields = ("title", "message", "user_email", "entity_label")
    readonly_fields = ("id", "created_at", "updated_at", "read_at")