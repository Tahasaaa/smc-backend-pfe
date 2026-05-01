from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import (
    NotificationCreateSerializer,
    NotificationSerializer,
    NotificationUnreadCountSerializer,
)


def _get_request_user_info(request):
    token_user = request.user
    user_id = getattr(token_user, "id", None) or getattr(token_user, "user_id", None)
    user_email = getattr(token_user, "email", "") or ""

    return {
        "user_id": user_id,
        "user_email": user_email,
    }


def _current_user_notifications(request):
    user_info = _get_request_user_info(request)

    if not user_info["user_id"]:
        return None, Response(
            {"error": "Authenticated token does not contain user_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    queryset = Notification.objects.filter(
        user_id=user_info["user_id"],
        is_deleted=False,
    )

    return queryset, None


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def notification_list_create(request):
    user_info = _get_request_user_info(request)

    if not user_info["user_id"]:
        return Response(
            {"error": "Authenticated token does not contain user_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if request.method == "POST":
        serializer = NotificationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        notification = Notification.objects.create(
            user_id=user_info["user_id"],
            user_email=user_info["user_email"],
            title=serializer.validated_data["title"],
            message=serializer.validated_data["message"],
            severity=serializer.validated_data.get("severity", "info"),
            source=serializer.validated_data.get("source", "system"),
            entity_label=serializer.validated_data.get("entityLabel", ""),
            action=serializer.validated_data.get("action", {}),
            metadata=serializer.validated_data.get("metadata", {}),
            status="unread",
        )

        response_serializer = NotificationSerializer(notification)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    queryset, error_response = _current_user_notifications(request)
    if error_response:
        return error_response

    status_filter = request.query_params.get("status")
    severity_filter = request.query_params.get("severity")
    source_filter = request.query_params.get("source")
    limit = request.query_params.get("limit")

    if status_filter in ["read", "unread"]:
        queryset = queryset.filter(status=status_filter)

    if severity_filter in ["critical", "major", "warning", "info", "success"]:
        queryset = queryset.filter(severity=severity_filter)

    if source_filter in ["incident", "monitoring", "rca", "ai", "email", "system"]:
        queryset = queryset.filter(source=source_filter)

    queryset = queryset.order_by("-created_at")

    if limit:
        try:
            limit_value = max(1, min(int(limit), 100))
            queryset = queryset[:limit_value]
        except ValueError:
            pass

    serializer = NotificationSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notification_unread_count(request):
    queryset, error_response = _current_user_notifications(request)
    if error_response:
        return error_response

    payload = {
        "unreadCount": queryset.filter(status="unread").count(),
    }

    serializer = NotificationUnreadCountSerializer(payload)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def notification_mark_read(request, notification_id):
    queryset, error_response = _current_user_notifications(request)
    if error_response:
        return error_response

    notification = queryset.filter(id=notification_id).first()

    if not notification:
        return Response(
            {"error": "Notification not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    notification.status = "read"
    notification.read_at = timezone.now()
    notification.save(update_fields=["status", "read_at", "updated_at"])

    serializer = NotificationSerializer(notification)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def notification_mark_unread(request, notification_id):
    queryset, error_response = _current_user_notifications(request)
    if error_response:
        return error_response

    notification = queryset.filter(id=notification_id).first()

    if not notification:
        return Response(
            {"error": "Notification not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    notification.status = "unread"
    notification.read_at = None
    notification.save(update_fields=["status", "read_at", "updated_at"])

    serializer = NotificationSerializer(notification)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def notification_mark_all_read(request):
    queryset, error_response = _current_user_notifications(request)
    if error_response:
        return error_response

    now = timezone.now()

    updated_count = queryset.filter(status="unread").update(
        status="read",
        read_at=now,
        updated_at=now,
    )

    return Response(
        {
            "updatedCount": updated_count,
            "message": "All notifications marked as read.",
        },
        status=status.HTTP_200_OK,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def notification_delete(request, notification_id):
    queryset, error_response = _current_user_notifications(request)
    if error_response:
        return error_response

    notification = queryset.filter(id=notification_id).first()

    if not notification:
        return Response(
            {"error": "Notification not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    notification.is_deleted = True
    notification.updated_at = timezone.now()
    notification.save(update_fields=["is_deleted", "updated_at"])

    return Response(status=status.HTTP_204_NO_CONTENT)