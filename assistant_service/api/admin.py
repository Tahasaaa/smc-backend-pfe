from django.contrib import admin
from .models import AssistantConversation, AssistantMessage, AssistantFeedback


@admin.register(AssistantConversation)
class AssistantConversationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "user_id",
        "user_email",
        "mode",
        "is_archived",
        "last_message_at",
        "updated_at",
    )
    search_fields = ("title", "user_email")
    list_filter = ("mode", "is_archived", "created_at", "updated_at")


@admin.register(AssistantMessage)
class AssistantMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conversation",
        "role",
        "mode",
        "model_name",
        "is_training_candidate",
        "created_at",
    )
    search_fields = ("content", "model_name")
    list_filter = ("role", "mode", "is_training_candidate", "created_at")


@admin.register(AssistantFeedback)
class AssistantFeedbackAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "message",
        "user_id",
        "user_email",
        "rating",
        "use_for_finetuning",
        "created_at",
    )
    search_fields = ("user_email", "corrected_answer", "notes")
    list_filter = ("rating", "use_for_finetuning", "created_at")