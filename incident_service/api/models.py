from django.db import models


class Incident(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('acknowledged', 'Acknowledged'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]

    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('major', 'Major'),
        ('minor', 'Minor'),
        ('warning', 'Warning'),
    ]

    ticket_number = models.CharField(max_length=100, unique=True, null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)

    source = models.CharField(max_length=100, default='imported_ticket')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='open')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='major')
    priority = models.CharField(max_length=20, null=True, blank=True)

    problem_family = models.CharField(max_length=150, null=True, blank=True)
    ticket_type = models.CharField(max_length=150, null=True, blank=True)

    site_name = models.CharField(max_length=150, null=True, blank=True)
    region_code = models.CharField(max_length=20, null=True, blank=True)
    technology = models.CharField(max_length=10, default='3G')

    assigned_team = models.CharField(max_length=150, null=True, blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    health_impact_score = models.FloatField(null=True, blank=True)
    root_cause_hint = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'incident'
        ordering = ['-started_at', '-created_at']

    def __str__(self):
        return self.title