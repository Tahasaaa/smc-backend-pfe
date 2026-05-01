from django.urls import path
from .cartography_views import (
    cartography_sites,
    cartography_sites_basic,
    cartography_summary,
    cartography_regions,
    cartography_filter_options,
    cartography_site_detail,
)

urlpatterns = [
    path('cartography/sites/', cartography_sites, name='cartography_sites'),
    path('cartography/sites-basic/', cartography_sites_basic, name='cartography_sites_basic'),
    path('cartography/summary/', cartography_summary, name='cartography_summary'),
    path('cartography/regions/', cartography_regions, name='cartography_regions'),
    path('cartography/filter-options/', cartography_filter_options, name='cartography_filter_options'),
    path('cartography/site/<path:nodeb_name>/', cartography_site_detail, name='cartography_site_detail'),
]