from django.urls import path

from .views import (
    notification_delete,
    notification_list_create,
    notification_mark_all_read,
    notification_mark_read,
    notification_mark_unread,
    notification_unread_count,
)

urlpatterns = [
    path("notifications/", notification_list_create, name="notification_list_create"),
    path(
        "notifications/unread-count/",
        notification_unread_count,
        name="notification_unread_count",
    ),
    path(
        "notifications/read-all/",
        notification_mark_all_read,
        name="notification_mark_all_read",
    ),
    path(
        "notifications/<uuid:notification_id>/read/",
        notification_mark_read,
        name="notification_mark_read",
    ),
    path(
        "notifications/<uuid:notification_id>/unread/",
        notification_mark_unread,
        name="notification_mark_unread",
    ),
    path(
        "notifications/<uuid:notification_id>/",
        notification_delete,
        name="notification_delete",
    ),
]