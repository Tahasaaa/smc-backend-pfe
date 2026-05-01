from django.urls import path
from .views import (
    assistant_chat,
    assistant_conversation_archive,
    assistant_conversation_delete,
    assistant_conversation_list,
    assistant_conversation_messages,
    assistant_conversation_rename,
    assistant_message_feedback,
)

urlpatterns = [
    path("assistant/chat/", assistant_chat, name="assistant_chat"),
    path("assistant/conversations/", assistant_conversation_list, name="assistant_conversation_list"),
    path(
        "assistant/conversations/<int:conversation_id>/messages/",
        assistant_conversation_messages,
        name="assistant_conversation_messages",
    ),
    path(
        "assistant/conversations/<int:conversation_id>/rename/",
        assistant_conversation_rename,
        name="assistant_conversation_rename",
    ),
    path(
        "assistant/conversations/<int:conversation_id>/archive/",
        assistant_conversation_archive,
        name="assistant_conversation_archive",
    ),
    path(
        "assistant/conversations/<int:conversation_id>/",
        assistant_conversation_delete,
        name="assistant_conversation_delete",
    ),
    path(
        "assistant/messages/<int:message_id>/feedback/",
        assistant_message_feedback,
        name="assistant_message_feedback",
    ),
]