from django.contrib import admin
from .models import (
    Site3G,
    Cell3G,
    SiteKpiMap3G,
    RegionKpi3G,
    SiteOperationalView3G,
)


@admin.register(Site3G)
class Site3GAdmin(admin.ModelAdmin):
    list_display = ("nodeb_name", "rnc_name", "latitude", "longitude", "cell_count", "active")
    search_fields = ("nodeb_name", "nodeb_name_norm", "rnc_name")
    list_filter = ("rnc_name", "active")


@admin.register(Cell3G)
class Cell3GAdmin(admin.ModelAdmin):
    list_display = ("cell_name", "nodeb_name", "rnc_name", "psc", "uarfcn_dl", "active")
    search_fields = ("cell_name", "cell_name_norm", "nodeb_name", "nodeb_name_norm")
    list_filter = ("rnc_name", "active")


@admin.register(SiteKpiMap3G)
class SiteKpiMap3GAdmin(admin.ModelAdmin):
    list_display = ("date", "nodeb_name", "rnc_name", "health_score", "status")
    search_fields = ("nodeb_name", "nodeb_name_norm", "rnc_name")
    list_filter = ("status", "rnc_name", "date")


@admin.register(RegionKpi3G)
class RegionKpi3GAdmin(admin.ModelAdmin):
    list_display = ("date", "rnc_name", "site_count", "avg_health_score", "good_sites", "warning_sites", "critical_sites")
    search_fields = ("rnc_name",)
    list_filter = ("date", "rnc_name")


@admin.register(SiteOperationalView3G)
class SiteOperationalView3GAdmin(admin.ModelAdmin):
    list_display = ("date", "nodeb_name", "rnc_name", "health_score", "status", "active_incident_count")
    search_fields = ("nodeb_name", "nodeb_name_norm", "rnc_name")
    list_filter = ("status", "rnc_name", "date")