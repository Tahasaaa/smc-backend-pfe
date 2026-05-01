from django.urls import path
from . import views

urlpatterns = [
    path('map/', views.map_overview, name='map_overview'),
    path('sites/', views.sites_list, name='sites_list'),
    path('kpi/trend/', views.kpi_trend, name='kpi_trend'),
    path('kpi/region_summary/', views.kpi_region_summary, name='kpi_region_summary'),
    path('governorates/', views.governorates_list, name='governorates_list'),
    path('kpi/worst-cells/', views.worst_cells, name='worst_cells'),
    path('filters/options/', views.filter_options, name='filter_options'),
]
