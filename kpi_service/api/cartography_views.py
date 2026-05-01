from django.db.models import Max
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import SiteKpiMap3G, RegionKpi3G, SiteOperationalView3G, Site3G, Cell3G
from .serializers import (
    SiteKpiMap3GSerializer,
    RegionKpi3GSerializer,
    SiteOperationalView3GSerializer,
    Site3GSerializer,
    Cell3GSerializer,
)


def get_selected_date(queryset, request):
    date_param = request.GET.get("date")

    if date_param:
        qs = queryset.filter(date__date=date_param)
        if qs.exists():
            return qs, date_param

    latest = queryset.aggregate(latest_date=Max("date"))["latest_date"]
    if latest is None:
        return queryset.none(), None

    return queryset.filter(date=latest), latest


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cartography_sites(request):
    qs = SiteOperationalView3G.objects.all()
    qs, selected_date = get_selected_date(qs, request)

    status_filter = request.GET.get("status")
    rnc_name = request.GET.get("rnc_name")
    search = request.GET.get("search")
    limit = request.GET.get("limit")

    if status_filter:
        qs = qs.filter(status=status_filter)
    if rnc_name:
        qs = qs.filter(rnc_name=rnc_name)
    if search:
        qs = qs.filter(nodeb_name__icontains=search)

    qs = qs.order_by("nodeb_name")

    if limit:
        try:
            qs = qs[:int(limit)]
        except ValueError:
            pass

    serializer = SiteOperationalView3GSerializer(qs, many=True)

    return Response({
        "technology": "3G",
        "selected_date": selected_date,
        "count": qs.count() if hasattr(qs, "count") else len(qs),
        "results": serializer.data
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cartography_sites_basic(request):
    qs = SiteKpiMap3G.objects.all()
    qs, selected_date = get_selected_date(qs, request)

    status_filter = request.GET.get("status")
    rnc_name = request.GET.get("rnc_name")
    search = request.GET.get("search")
    limit = request.GET.get("limit")

    if status_filter:
        qs = qs.filter(status=status_filter)
    if rnc_name:
        qs = qs.filter(rnc_name=rnc_name)
    if search:
        qs = qs.filter(nodeb_name__icontains=search)

    qs = qs.order_by("nodeb_name")

    if limit:
        try:
            qs = qs[:int(limit)]
        except ValueError:
            pass

    serializer = SiteKpiMap3GSerializer(qs, many=True)

    return Response({
        "technology": "3G",
        "selected_date": selected_date,
        "count": qs.count() if hasattr(qs, "count") else len(qs),
        "results": serializer.data
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cartography_summary(request):
    qs = SiteOperationalView3G.objects.all()
    qs, selected_date = get_selected_date(qs, request)

    status_filter = request.GET.get("status")
    rnc_name = request.GET.get("rnc_name")

    if status_filter:
        qs = qs.filter(status=status_filter)
    if rnc_name:
        qs = qs.filter(rnc_name=rnc_name)

    total_sites = qs.count()
    good_sites = qs.filter(status="good").count()
    warning_sites = qs.filter(status="warning").count()
    critical_sites = qs.filter(status="critical").count()
    unknown_sites = qs.filter(status="unknown").count()

    return Response({
        "technology": "3G",
        "selected_date": selected_date,
        "total_sites": total_sites,
        "good_sites": good_sites,
        "warning_sites": warning_sites,
        "critical_sites": critical_sites,
        "unknown_sites": unknown_sites,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cartography_regions(request):
    qs = RegionKpi3G.objects.all()
    qs, selected_date = get_selected_date(qs, request)

    rnc_name = request.GET.get("rnc_name")
    if rnc_name:
        qs = qs.filter(rnc_name=rnc_name)

    serializer = RegionKpi3GSerializer(qs.order_by("rnc_name"), many=True)

    return Response({
        "technology": "3G",
        "selected_date": selected_date,
        "aggregation_level": "rnc",
        "count": qs.count(),
        "results": serializer.data
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cartography_filter_options(request):
    site_qs = SiteOperationalView3G.objects.all()

    available_dates = (
        site_qs.exclude(date__isnull=True)
        .values_list("date", flat=True)
        .distinct()
        .order_by("-date")
    )

    formatted_dates = []
    for dt in available_dates:
        if dt:
            formatted_dates.append(dt.date().isoformat())

    rnc_names = list(
        site_qs.exclude(rnc_name__isnull=True)
        .exclude(rnc_name="")
        .values_list("rnc_name", flat=True)
        .distinct()
        .order_by("rnc_name")
    )

    statuses = list(
        site_qs.exclude(status__isnull=True)
        .exclude(status="")
        .values_list("status", flat=True)
        .distinct()
        .order_by("status")
    )

    return Response({
        "technology": "3G",
        "dates": formatted_dates,
        "rnc_names": rnc_names,
        "statuses": statuses
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cartography_site_detail(request, nodeb_name):
    op_qs = SiteOperationalView3G.objects.filter(nodeb_name=nodeb_name)
    op_qs, selected_date = get_selected_date(op_qs, request)

    site_op = op_qs.first()
    if not site_op:
        return Response({"error": "Site not found"}, status=status.HTTP_404_NOT_FOUND)

    site_meta = Site3G.objects.filter(nodeb_name_norm=site_op.nodeb_name_norm).first()
    cells = Cell3G.objects.filter(nodeb_name_norm=site_op.nodeb_name_norm).order_by("cell_name")

    site_payload = SiteOperationalView3GSerializer(site_op).data
    site_meta_payload = Site3GSerializer(site_meta).data if site_meta else None
    cells_payload = Cell3GSerializer(cells[:50], many=True).data

    return Response({
        "technology": "3G",
        "selected_date": selected_date,
        "site": site_payload,
        "site_metadata": site_meta_payload,
        "cells_count": cells.count(),
        "cells_preview": cells_payload
    })