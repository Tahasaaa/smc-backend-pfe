from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Incident
from .serializers import IncidentListSerializer, IncidentDetailSerializer


def apply_incident_filters(queryset, request):
    status_value = request.GET.get('status')
    severity = request.GET.get('severity')
    priority = request.GET.get('priority')
    technology = request.GET.get('technology')
    region_code = request.GET.get('region_code')
    site_name = request.GET.get('site_name')
    problem_family = request.GET.get('problem_family')
    search = request.GET.get('search')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    is_active = request.GET.get('is_active')

    if status_value:
        queryset = queryset.filter(status=status_value)
    if severity:
        queryset = queryset.filter(severity=severity)
    if priority:
        queryset = queryset.filter(priority=priority)
    if technology:
        queryset = queryset.filter(technology=technology)
    if region_code:
        queryset = queryset.filter(region_code=region_code)
    if site_name:
        queryset = queryset.filter(site_name__icontains=site_name)
    if problem_family:
        queryset = queryset.filter(problem_family__icontains=problem_family)
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search) |
            Q(description__icontains=search) |
            Q(ticket_number__icontains=search) |
            Q(site_name__icontains=search) |
            Q(region_code__icontains=search)
        )
    if date_from:
        queryset = queryset.filter(started_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(started_at__date__lte=date_to)
    if is_active is not None:
        if is_active.lower() == 'true':
            queryset = queryset.filter(is_active=True)
        elif is_active.lower() == 'false':
            queryset = queryset.filter(is_active=False)

    return queryset


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def incidents_list(request):
    qs = Incident.objects.all()
    qs = apply_incident_filters(qs, request)

    limit = request.GET.get('limit', 20)
    offset = request.GET.get('offset', 0)

    try:
        limit = int(limit)
        offset = int(offset)
    except ValueError:
        return Response({'error': 'limit and offset must be integers'}, status=status.HTTP_400_BAD_REQUEST)

    total = qs.count()
    qs = qs[offset:offset + limit]

    serializer = IncidentListSerializer(qs, many=True)
    return Response({
        'count': total,
        'limit': limit,
        'offset': offset,
        'results': serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def incidents_overview(request):
    qs = Incident.objects.filter(is_active=True).order_by('-health_impact_score', '-started_at')[:15]
    serializer = IncidentListSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def incident_detail(request, incident_id):
    try:
        incident = Incident.objects.get(id=incident_id)
    except Incident.DoesNotExist:
        return Response({'error': 'Incident not found'}, status=status.HTTP_404_NOT_FOUND)

    serializer = IncidentDetailSerializer(incident)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def incident_stats(request):
    qs = Incident.objects.all()

    return Response({
        'active_incidents': qs.filter(is_active=True).count(),
        'critical_incidents': qs.filter(severity='critical', is_active=True).count(),
        'major_incidents': qs.filter(severity='major', is_active=True).count(),
        'minor_incidents': qs.filter(severity='minor', is_active=True).count(),
        'resolved_incidents': qs.filter(status='resolved').count(),
        'closed_incidents': qs.filter(status='closed').count(),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def incident_filter_options(request):
    qs = Incident.objects.all()

    return Response({
        'statuses': [x for x in qs.values_list('status', flat=True).distinct() if x],
        'severities': [x for x in qs.values_list('severity', flat=True).distinct() if x],
        'priorities': [x for x in qs.values_list('priority', flat=True).distinct() if x],
        'technologies': [x for x in qs.values_list('technology', flat=True).distinct() if x],
        'regions': [x for x in qs.values_list('region_code', flat=True).distinct() if x],
        'problem_families': [x for x in qs.values_list('problem_family', flat=True).distinct() if x],
    })