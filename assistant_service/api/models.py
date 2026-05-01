from django.db import models


ASSISTANT_MODE_CHOICES = [
    ("general", "General"),
    ("incident", "Incident"),
    ("rca", "RCA"),
    ("email", "Email"),
    ("monitoring", "Monitoring"),
    ("map", "Map"),
]

ASSISTANT_ROLE_CHOICES = [
    ("user", "User"),
    ("assistant", "Assistant"),
    ("system", "System"),
]


class AssistantConversation(models.Model):
    title = models.CharField(max_length=255, blank=True, default="New conversation")
    user_id = models.IntegerField(db_index=True)
    user_email = models.EmailField(blank=True, default="", db_index=True)
    mode = models.CharField(
        max_length=20,
        choices=ASSISTANT_MODE_CHOICES,
        default="general",
        db_index=True,
    )
    is_archived = models.BooleanField(default=False, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "assistant_conversation"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} ({self.user_email or self.user_id})"


class AssistantMessage(models.Model):
    conversation = models.ForeignKey(
        AssistantConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(
        max_length=20,
        choices=ASSISTANT_ROLE_CHOICES,
        db_index=True,
    )
    mode = models.CharField(
        max_length=20,
        choices=ASSISTANT_MODE_CHOICES,
        default="general",
        db_index=True,
    )
    content = models.TextField()

    context_snapshot = models.JSONField(default=dict, blank=True)
    parsed_payload = models.JSONField(default=dict, blank=True)

    model_name = models.CharField(max_length=255, blank=True, default="")
    prompt_version = models.CharField(max_length=100, blank=True, default="v1")

    is_training_candidate = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "assistant_message"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role} - conv:{self.conversation_id} - {self.created_at}"


class AssistantFeedback(models.Model):
    message = models.ForeignKey(
        AssistantMessage,
        on_delete=models.CASCADE,
        related_name="feedback_items",
    )
    user_id = models.IntegerField(db_index=True)
    user_email = models.EmailField(blank=True, default="", db_index=True)

    rating = models.SmallIntegerField(null=True, blank=True)
    corrected_answer = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    use_for_finetuning = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "assistant_feedback"
        ordering = ["-created_at"]

    def __str__(self):
        return f"feedback for message {self.message_id}"