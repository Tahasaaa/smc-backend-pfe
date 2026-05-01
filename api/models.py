from django.db import models
from django.utils import timezone
from datetime import timedelta


class Role(models.Model):
    role = models.CharField(max_length=100)
    permissions = models.JSONField(default=list)

    class Meta:
        db_table = 'role'


class User(models.Model):
    fullname = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        db_column='id_role'
    )

    class Meta:
        db_table = 'user'


class VerificationCode(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='verification_codes'
    )
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = 'verification_code'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)
        super().save(*args, **kwargs)


class AuthLog(models.Model):
    ACTION_CHOICES = [
        ('login_success', 'Login Success'),
        ('login_failed', 'Login Failed'),
        ('verification_code_sent', 'Verification Code Sent'),
        ('verification_success', 'Verification Success'),
        ('verification_failed', 'Verification Failed'),
        ('logout', 'Logout'),
        ('get_user', 'Get User'),
        ('delete_user', 'Delete User'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    email = models.EmailField(null=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    ip = models.GenericIPAddressField(null=True)
    user_agent = models.CharField(max_length=255, null=True)
    detail = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'auth_log'
        ordering = ['-created_at']