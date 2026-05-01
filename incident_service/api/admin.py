from django.contrib import admin
from .models import Incident


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket_number', 'title', 'severity', 'status', 'site_name', 'started_at')
    search_fields = ('ticket_number', 'title', 'description', 'site_name', 'region_code')
    list_filter = ('severity', 'status', 'technology', 'problem_family')