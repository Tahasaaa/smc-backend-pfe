from django.urls import path
from .views import (
    incidents_list,
    incidents_overview,
    incident_detail,
    incident_stats,
    incident_filter_options,
)

urlpatterns = [
    path('incidents/', incidents_list, name='incidents_list'),
    path('incidents/overview/', incidents_overview, name='incidents_overview'),
    path('incidents/stats/', incident_stats, name='incident_stats'),
    path('incidents/filter-options/', incident_filter_options, name='incident_filter_options'),
    path('incidents/<int:incident_id>/', incident_detail, name='incident_detail'),
]