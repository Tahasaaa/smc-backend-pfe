from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)
    readAt = serializers.DateTimeField(source="read_at", read_only=True, allow_null=True)
    entityLabel = serializers.CharField(source="entity_label", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "severity",
            "source",
            "status",
            "createdAt",
            "updatedAt",
            "readAt",
            "entityLabel",
            "action",
            "metadata",
        ]


class NotificationCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    message = serializers.CharField()
    severity = serializers.ChoiceField(
        choices=["critical", "major", "warning", "info", "success"],
        required=False,
        default="info",
    )
    source = serializers.ChoiceField(
        choices=["incident", "monitoring", "rca", "ai", "email", "system"],
        required=False,
        default="system",
    )
    entityLabel = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=255,
    )
    action = serializers.JSONField(required=False, default=dict)
    metadata = serializers.JSONField(required=False, default=dict)


class NotificationUnreadCountSerializer(serializers.Serializer):
    unreadCount = serializers.IntegerField()