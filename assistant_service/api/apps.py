from django.apps import AppConfig


class AssistantApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
    label = "assistant_api"
    verbose_name = "Assistant API"