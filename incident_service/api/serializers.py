from rest_framework import serializers
from .models import Incident


class IncidentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Incident
        fields = [
            'id',
            'ticket_number',
            'title',
            'status',
            'severity',
            'priority',
            'problem_family',
            'site_name',
            'region_code',
            'technology',
            'started_at',
            'is_active',
            'health_impact_score',
            'root_cause_hint',
        ]


class IncidentDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Incident
        fields = '__all__'