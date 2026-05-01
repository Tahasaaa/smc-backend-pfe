from django.db import models


class Profile(models.Model):
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, blank=True, default="")
    role = models.CharField(max_length=100, blank=True, default="NOC Engineer")
    timezone = models.CharField(max_length=100, blank=True, default="Africa/Tunis")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username