from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate

from .models import Governorate, NetworkSite, KpiRecord
from .serializers import (
    GovernorateSerializer,
    NetworkSiteSerializer,
    KpiRecordSerializer,
    GovernorateMapSerializer,
)


def get_filters(request):
    """Extract common filters from request query params."""
    return {
        'technology':  request.GET.get('technology', '3G'),
        'date_from':   request.GET.get('date_from'),
        'date_to':     request.GET.get('date_to'),
        'region_code': request.GET.get('region_code'),
        'rnc':         request.GET.get('rnc'),
        'nodeb_name':  request.GET.get('nodeb_name'),
    }


def apply_filters(queryset, filters):
    """Apply common filters to any KpiRecord queryset."""
    if filters['technology']:
        queryset = queryset.filter(technology=filters['technology'])
    if filters['date_from']:
        queryset = queryset.filter(date__gte=filters['date_from'])
    if filters['date_to']:
        queryset = queryset.filter(date__lte=filters['date_to'])
    if filters['region_code']:
        queryset = queryset.filter(region_code=filters['region_code'])
    if filters['rnc']:
        queryset = queryset.filter(rnc=filters['rnc'])
    if filters['nodeb_name']:
        queryset = queryset.filter(nodeb_name=filters['nodeb_name'])
    return queryset


# ============================================================
# GET /api/map/
# Returns KPI summary per governorate for the choropleth map
# ============================================================
@api_view(['GET'])
def map_overview(request):
    filters = get_filters(request)
    qs = apply_filters(KpiRecord.objects.all(), filters)

    # Aggregate per region
    regional = qs.values('region_code').annotate(
        avg_cssr_ps        = Avg('cssr_ps'),
        avg_ps_rab_sr      = Avg('ps_rab_setup_sr'),
        avg_throughput     = Avg('throughput_3g'),
        avg_iub_congestion = Avg('iub_congestion'),
        avg_call_drop      = Avg('call_drop_dch'),
        site_count         = Count('nodeb_name', distinct=True),
    )

    # Join with governorate for lat/lon
    gov_map = {
        g.region_code: g
        for g in Governorate.objects.all()
    }

    results = []
    for r in regional:
        gov = gov_map.get(r['region_code'])
        if not gov:
            continue

        # Compute health score (0-100)
        cssr    = r['avg_cssr_ps']        or 0
        rab_sr  = r['avg_ps_rab_sr']      or 0
        tput    = r['avg_throughput']      or 0
        iub     = r['avg_iub_congestion']  or 0
        drop    = r['avg_call_drop']       or 0

        health = (
            (cssr   / 100 * 30) +
            (rab_sr / 100 * 30) +
            (min(tput, 100) / 100 * 20) +
            (max(0, (10 - iub) / 10) * 10) +
            (max(0, (5  - drop) / 5)  * 10)
        )

        results.append({
            'region_code':       r['region_code'],
            'name_fr':           gov.name_fr,
            'name_ar':           gov.name_ar,
            'latitude':          gov.latitude,
            'longitude':         gov.longitude,
            'avg_cssr_ps':       round(cssr,   2),
            'avg_ps_rab_sr':     round(rab_sr, 2),
            'avg_throughput':    round(tput,   2),
            'avg_iub_congestion':round(iub,    2),
            'avg_call_drop':     round(drop,   2),
            'site_count':        r['site_count'],
            'health_score':      round(min(health, 100), 1),
        })

    return Response(results)


# ============================================================
# GET /api/sites/
# Returns all sites with their latest KPI snapshot
# ============================================================
@api_view(['GET'])
def sites_list(request):
    filters = get_filters(request)
    qs = apply_filters(KpiRecord.objects.all(), filters)

    sites = qs.values(
        'nodeb_name', 'rnc', 'region_code', 'technology'
    ).annotate(
        avg_cssr_ps    = Avg('cssr_ps'),
        avg_ps_rab_sr  = Avg('ps_rab_setup_sr'),
        avg_throughput = Avg('throughput_3g'),
        avg_iub        = Avg('iub_congestion'),
        avg_drop       = Avg('call_drop_dch'),
        record_count   = Count('id'),
    ).order_by('nodeb_name')

    return Response(list(sites))


# ============================================================
# GET /api/kpi/trend/
# Returns daily trend for a specific KPI
# ============================================================
@api_view(['GET'])
def kpi_trend(request):
    filters  = get_filters(request)
    kpi_name = request.GET.get('kpi', 'cssr_ps')

    ALLOWED_KPIS = [
        'cssr_ps', 'ps_rab_setup_sr', 'throughput_3g',
        'hsdpa_tput_per_user', 'iub_congestion', 'call_drop_dch',
        'ce_congestion', 'radio_congestion', 'sho_avg_ecno',
        'mean_rtwp', 'ho_3g_2g_voice', 'evqi',
    ]

    if kpi_name not in ALLOWED_KPIS:
        return Response(
            {'error': f'KPI not allowed. Choose from: {ALLOWED_KPIS}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    qs = apply_filters(KpiRecord.objects.all(), filters)

    trend = (
        qs.values('date')
        .annotate(value=Avg(kpi_name))
        .order_by('date')
    )

    return Response([
        {'date': t['date'], 'value': round(t['value'] or 0, 4)}
        for t in trend
    ])


# ============================================================
# GET /api/kpi/region_summary/
# Returns KPI averages per RNC or per region
# ============================================================
@api_view(['GET'])
def kpi_region_summary(request):
    filters  = get_filters(request)
    group_by = request.GET.get('group_by', 'region_code')

    if group_by not in ['region_code', 'rnc', 'nodeb_name']:
        group_by = 'region_code'

    qs = apply_filters(KpiRecord.objects.all(), filters)

    summary = qs.values(group_by).annotate(
        avg_cssr_ps         = Avg('cssr_ps'),
        avg_ps_rab_sr       = Avg('ps_rab_setup_sr'),
        avg_throughput      = Avg('throughput_3g'),
        avg_hsdpa_tput      = Avg('hsdpa_tput_per_user'),
        avg_iub_congestion  = Avg('iub_congestion'),
        avg_ce_congestion   = Avg('ce_congestion'),
        avg_call_drop_dch   = Avg('call_drop_dch'),
        avg_sho_ecno        = Avg('sho_avg_ecno'),
        avg_mean_rtwp       = Avg('mean_rtwp'),
        avg_ho_voice        = Avg('ho_3g_2g_voice'),
        record_count        = Count('id'),
    ).order_by(group_by)

    return Response(list(summary))


# ============================================================
# GET /api/governorates/
# Returns all governorates
# ============================================================
@api_view(['GET'])
def governorates_list(request):
    govs = Governorate.objects.all().order_by('name_fr')
    return Response(GovernorateSerializer(govs, many=True).data)


# ============================================================
# GET /api/kpi/worst-cells/
# Returns worst performing cells based on health score
# ============================================================
@api_view(['GET'])
def worst_cells(request):
    filters = get_filters(request)
    qs      = apply_filters(KpiRecord.objects.all(), filters)
    limit   = int(request.GET.get('limit', 20))

    cells = qs.values(
        'nodeb_name', 'rnc', 'region_code'
    ).annotate(
        avg_cssr_ps    = Avg('cssr_ps'),
        avg_ps_rab_sr  = Avg('ps_rab_setup_sr'),
        avg_throughput = Avg('throughput_3g'),
        avg_iub        = Avg('iub_congestion'),
        avg_drop       = Avg('call_drop_dch'),
    )

    # Compute health score and sort
    result = []
    for c in cells:
        cssr   = c['avg_cssr_ps']    or 0
        rab_sr = c['avg_ps_rab_sr']  or 0
        tput   = c['avg_throughput'] or 0
        iub    = c['avg_iub']        or 0
        drop   = c['avg_drop']       or 0

        health = (
            (cssr   / 100 * 30) +
            (rab_sr / 100 * 30) +
            (min(tput, 100) / 100 * 20) +
            (max(0, (10 - iub) / 10) * 10) +
            (max(0, (5  - drop) / 5)  * 10)
        )

        result.append({
            **c,
            'health_score': round(min(health, 100), 1)
        })

    result.sort(key=lambda x: x['health_score'])
    return Response(result[:limit])


# ============================================================
# GET /api/filters/options/
# Returns available filter options (RNCs, regions, dates)
# ============================================================
@api_view(['GET'])
def filter_options(request):
    technology = request.GET.get('technology', '3G')
    qs = KpiRecord.objects.filter(technology=technology)

    return Response({
        'technologies': ['3G', '4G', '5G'],
        'rncs':         list(qs.values_list('rnc', flat=True).distinct()),
        'region_codes': list(qs.values_list('region_code', flat=True).distinct()),
        'date_min':     qs.order_by('date').values_list('date', flat=True).first(),
        'date_max':     qs.order_by('-date').values_list('date', flat=True).first(),
    })