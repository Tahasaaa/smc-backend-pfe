import pandas as pd
from django.core.management.base import BaseCommand
from api.models import Incident


def clean_value(value):
    if pd.isna(value):
        return None
    value = str(value).strip()
    return value if value else None


def parse_dt(value):
    if pd.isna(value) or value is None:
        return None
    try:
        dt = pd.to_datetime(value, errors='coerce')
        if pd.isna(dt):
            return None
        return dt.to_pydatetime()
    except Exception:
        return None


def map_status(raw_status):
    if not raw_status:
        return 'open'
    s = raw_status.strip().lower()

    if 'clôt' in s or 'clos' in s or 'closed' in s:
        return 'closed'
    if 'répar' in s or 'resolved' in s:
        return 'resolved'
    if 'ack' in s or 'acquitt' in s:
        return 'acknowledged'
    if 'progress' in s or 'cours' in s:
        return 'in_progress'
    return 'open'


def map_severity(priority):
    if not priority:
        return 'major'

    p = str(priority).strip().lower()
    if p in ['p1', '1', 'critical', 'critique']:
        return 'critical'
    if p in ['p2', '2', 'major']:
        return 'major'
    if p in ['p3', '3', 'minor']:
        return 'minor'
    return 'warning'


def compute_is_active(status):
    return status not in ['resolved', 'closed']


def compute_health_impact_score(severity):
    mapping = {
        'critical': 90.0,
        'major': 70.0,
        'minor': 40.0,
        'warning': 20.0,
    }
    return mapping.get(severity, 50.0)


def infer_root_cause(problem_family, description):
    text = f"{problem_family or ''} {description or ''}".lower()

    if 'transport' in text or 'transmission' in text:
        return 'Probable transmission/transport issue'
    if 'radio' in text:
        return 'Probable radio degradation'
    if 'congestion' in text:
        return 'Probable congestion'
    if 'power' in text or 'energy' in text or 'alim' in text:
        return 'Probable power issue'
    if 'core' in text:
        return 'Probable core network issue'
    return 'Root cause under analysis'


def build_title(problem_family, site_name, description):
    if problem_family and site_name:
        return f"{problem_family} - {site_name}"
    if problem_family:
        return f"{problem_family} incident"
    if site_name:
        return f"Incident - {site_name}"
    if description:
        return description[:120]
    return "Imported incident"


class Command(BaseCommand):
    help = 'Import incidents from Excel file'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str)

    def handle(self, *args, **options):
        file_path = options['file_path']

        df = pd.read_excel(file_path)
        created_count = 0
        updated_count = 0

        for _, row in df.iterrows():
            ticket_number = clean_value(row.get('Numéro ticket'))
            description = clean_value(row.get('Description'))
            problem_family = clean_value(row.get('Famille de problèmes'))
            ticket_type = clean_value(row.get('Type ticket'))
            priority = clean_value(row.get('Priorité'))
            raw_status = clean_value(row.get('Etat'))
            source = clean_value(row.get('Origine')) or 'imported_ticket'
            assigned_team = clean_value(row.get('EDS Pilote'))
            site_name = clean_value(row.get('Nom du site'))

            started_at = parse_dt(row.get('Date début'))
            acknowledged_at = parse_dt(row.get("Date d'acquittement"))
            resolved_at = parse_dt(row.get('Date de réparation'))
            closed_at = parse_dt(row.get('Date de clôture'))

            status = map_status(raw_status)
            severity = map_severity(priority)
            is_active = compute_is_active(status)
            health_impact_score = compute_health_impact_score(severity)
            root_cause_hint = infer_root_cause(problem_family, description)
            title = build_title(problem_family, site_name, description)

            defaults = {
                'title': title,
                'description': description,
                'source': source,
                'status': status,
                'severity': severity,
                'priority': priority,
                'problem_family': problem_family,
                'ticket_type': ticket_type,
                'site_name': site_name,
                'region_code': None,
                'technology': '3G',
                'assigned_team': assigned_team,
                'started_at': started_at,
                'acknowledged_at': acknowledged_at,
                'resolved_at': resolved_at,
                'closed_at': closed_at,
                'is_active': is_active,
                'health_impact_score': health_impact_score,
                'root_cause_hint': root_cause_hint,
            }

            if ticket_number:
                _, created = Incident.objects.update_or_create(
                    ticket_number=ticket_number,
                    defaults=defaults
                )
            else:
                Incident.objects.create(
                    ticket_number=None,
                    **defaults
                )
                created = True

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Import finished. Created: {created_count}, Updated: {updated_count}'
        ))