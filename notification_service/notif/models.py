import uuid

from django.db import models


NOTIFICATION_SEVERITY_CHOICES = [
    ("critical", "Critical"),
    ("major", "Major"),
    ("warning", "Warning"),
    ("info", "Info"),
    ("success", "Success"),
]

NOTIFICATION_SOURCE_CHOICES = [
    ("incident", "Incident"),
    ("monitoring", "Monitoring"),
    ("rca", "RCA"),
    ("ai", "AI"),
    ("email", "Email"),
    ("system", "System"),
]

NOTIFICATION_STATUS_CHOICES = [
    ("unread", "Unread"),
    ("read", "Read"),
]


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user_id = models.IntegerField(db_index=True)
    user_email = models.EmailField(blank=True, default="", db_index=True)

    title = models.CharField(max_length=255)
    message = models.TextField()

    severity = models.CharField(
        max_length=20,
        choices=NOTIFICATION_SEVERITY_CHOICES,
        default="info",
        db_index=True,
    )
    source = models.CharField(
        max_length=20,
        choices=NOTIFICATION_SOURCE_CHOICES,
        default="system",
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=NOTIFICATION_STATUS_CHOICES,
        default="unread",
        db_index=True,
    )

    entity_label = models.CharField(max_length=255, blank=True, default="")
    action = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    is_deleted = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notification"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.user_email or self.user_id})"