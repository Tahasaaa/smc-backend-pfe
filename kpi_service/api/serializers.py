from rest_framework import serializers
from .models import (
    Governorate,
    NetworkSite,
    KpiRecord,
    Site3G,
    Cell3G,
    SiteKpiMap3G,
    RegionKpi3G,
    SiteOperationalView3G,
)


# =========================
# EXISTING KPI SERIALIZERS
# =========================

class GovernorateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Governorate
        fields = '__all__'


class GovernorateMapSerializer(serializers.Serializer):
    region_code = serializers.CharField()
    governorate = serializers.CharField()
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)
    avg_integrity = serializers.FloatField(allow_null=True)
    avg_availability_3g = serializers.FloatField(allow_null=True)
    avg_cssr_ps = serializers.FloatField(allow_null=True)
    avg_throughput_3g = serializers.FloatField(allow_null=True)
    avg_ps_rab_setup_sr = serializers.FloatField(allow_null=True)
    avg_iub_congestion = serializers.FloatField(allow_null=True)
    sites_count = serializers.IntegerField()


class NetworkSiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkSite
        fields = '__all__'


class KpiRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = KpiRecord
        fields = '__all__'


class SiteTrendSerializer(serializers.Serializer):
    date = serializers.DateField()
    avg_integrity = serializers.FloatField(allow_null=True)
    avg_availability_3g = serializers.FloatField(allow_null=True)
    avg_cssr_ps = serializers.FloatField(allow_null=True)
    avg_throughput_3g = serializers.FloatField(allow_null=True)
    avg_ps_rab_setup_sr = serializers.FloatField(allow_null=True)
    avg_iub_congestion = serializers.FloatField(allow_null=True)


class WorstCellSerializer(serializers.Serializer):
    cell_name = serializers.CharField()
    nodeb_name = serializers.CharField(allow_null=True)
    rnc = serializers.CharField(allow_null=True)
    region_code = serializers.CharField(allow_null=True)
    avg_cssr_ps = serializers.FloatField(allow_null=True)
    avg_throughput_3g = serializers.FloatField(allow_null=True)
    avg_ps_rab_setup_sr = serializers.FloatField(allow_null=True)
    avg_iub_congestion = serializers.FloatField(allow_null=True)


class RNCSummarySerializer(serializers.Serializer):
    rnc = serializers.CharField()
    avg_integrity = serializers.FloatField(allow_null=True)
    avg_availability_3g = serializers.FloatField(allow_null=True)
    avg_cssr_ps = serializers.FloatField(allow_null=True)
    avg_throughput_3g = serializers.FloatField(allow_null=True)
    avg_ps_rab_setup_sr = serializers.FloatField(allow_null=True)
    avg_iub_congestion = serializers.FloatField(allow_null=True)
    sites_count = serializers.IntegerField()


class FilterOptionsSerializer(serializers.Serializer):
    rncs = serializers.ListField(child=serializers.CharField())
    region_codes = serializers.ListField(child=serializers.CharField())
    governorates = serializers.ListField(child=serializers.CharField())
    technologies = serializers.ListField(child=serializers.CharField())


# =========================
# NEW 3G CARTOGRAPHY SERIALIZERS
# =========================

class Site3GSerializer(serializers.ModelSerializer):
    class Meta:
        model = Site3G
        fields = '__all__'


class Cell3GSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cell3G
        fields = '__all__'


class SiteKpiMap3GSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteKpiMap3G
        fields = [
            'date',
            'nodeb_name',
            'nodeb_name_norm',
            'rnc_name',
            'latitude',
            'longitude',
            'avg_cssr_ps',
            'avg_ps_rab_sr',
            'avg_throughput_3g',
            'avg_iub_congestion',
            'avg_drop_rate',
            'avg_availability_3g',
            'health_score',
            'status',
        ]


class RegionKpi3GSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegionKpi3G
        fields = '__all__'


class SiteOperationalView3GSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteOperationalView3G
        fields = [
            'date',
            'nodeb_name',
            'nodeb_name_norm',
            'rnc_name',
            'latitude',
            'longitude',
            'avg_cssr_ps',
            'avg_ps_rab_sr',
            'avg_throughput_3g',
            'avg_iub_congestion',
            'avg_drop_rate',
            'avg_availability_3g',
            'health_score',
            'status',
            'active_incident_count',
            'critical_incident_count',
            'last_incident_title',
            'main_kpi_issue',
        ]