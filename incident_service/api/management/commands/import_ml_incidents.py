import math
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.models import Incident


def clean_str(value, default=""):
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return str(value).strip()


def parse_datetime(value):
    text = clean_str(value)
    if not text:
        return None

    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)

    if pd.isna(parsed):
        return None

    dt = parsed.to_pydatetime()

    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())

    return dt


def map_status(value):
    text = clean_str(value).lower()

    if not text:
        return "open"

    if text in {"réparé", "repare", "repaired", "resolved"}:
        return "resolved"

    if text in {"clôturé", "cloture", "closed", "fermé", "ferme"}:
        return "closed"

    if text in {"acquitté", "acquitte", "acknowledged"}:
        return "acknowledged"

    if text in {"en cours", "in progress", "ongoing"}:
        return "in_progress"

    if text in {"ouvert", "open", "nouveau", "new"}:
        return "open"

    return "open"


def map_severity(priority_code, priority_text):
    code = clean_str(priority_code).upper()
    text = clean_str(priority_text).lower()

    if code == "P1" or "très critique" in text or "tres critique" in text:
        return "critical"

    if code == "P2" or "critique" in text or "élevée" in text or "elevee" in text:
        return "major"

    if code == "P3" or "moyenne" in text:
        return "warning"

    if code == "P4" or "faible" in text:
        return "minor"

    return "major"


def impact_score_from_priority(priority_code, priority_text):
    severity = map_severity(priority_code, priority_text)

    if severity == "critical":
        return 95.0
    if severity == "major":
        return 78.0
    if severity == "warning":
        return 55.0
    if severity == "minor":
        return 30.0

    return 50.0


def root_cause_from_description(description, priority_text):
    desc = clean_str(description).lower()
    priority = clean_str(priority_text).lower()

    if "charge" in desc or "load" in desc:
        return "Traffic/load anomaly suspected"

    if "antenne" in desc or "antenna" in desc:
        return "Radio antenna or RF configuration check recommended"

    if "param" in desc:
        return "Engineering parameter verification recommended"

    if "critique" in priority:
        return "Critical service degradation suspected"

    return "Radio QoS degradation suspected"


def build_title(ticket_number, site_name, priority_code, priority_text):
    site = clean_str(site_name, "Unknown site")
    code = clean_str(priority_code, "P?")
    text = clean_str(priority_text, "incident")

    return f"{code} {text} incident on {site} ({ticket_number})"


class Command(BaseCommand):
    help = "Import unified ML ticket dataset into incident operational table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tickets",
            default="data_import/tickets_radio_synthetic_linked.csv",
            help="Path to tickets CSV.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing incidents before import.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate CSV and print counts without writing to DB.",
        )

    def handle(self, *args, **options):
        base_dir = Path.cwd()

        tickets_path = Path(options["tickets"])
        if not tickets_path.is_absolute():
            tickets_path = base_dir / tickets_path

        if not tickets_path.exists():
            raise FileNotFoundError(f"Tickets CSV not found: {tickets_path}")

        self.stdout.write(self.style.NOTICE(f"Reading tickets CSV: {tickets_path}"))

        df = pd.read_csv(tickets_path)

        required_columns = [
            "Numéro ticket",
            "Date début",
            "Description",
            "Etat",
            "Famille de problèmes",
            "Type ticket",
            "Priorité",
            "Nom du site",
            "Priorite_Texte",
            "site_id",
        ]

        missing = [column for column in required_columns if column not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("CSV validation OK"))
        self.stdout.write(f"Ticket rows: {len(df)}")
        self.stdout.write(f"Unique sites: {df['site_id'].nunique()}")
        self.stdout.write(
            f"Priorities: {sorted(df['Priorité'].dropna().astype(str).unique().tolist())}"
        )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry-run mode: no DB changes applied."))
            return

        incidents = []

        for _, row in df.iterrows():
            ticket_number = clean_str(row.get("Numéro ticket"))
            site_name = clean_str(row.get("Nom du site")) or clean_str(row.get("site_id"))
            priority_code = clean_str(row.get("Priorité"))
            priority_text = clean_str(row.get("Priorite_Texte"))
            description = clean_str(row.get("Description"))

            if not ticket_number:
                continue

            started_at = parse_datetime(row.get("Date début"))
            acknowledged_at = parse_datetime(row.get("Date d'acquittement"))
            resolved_at = parse_datetime(row.get("Date de réparation"))
            closed_at = parse_datetime(row.get("Date de clôture"))

            status = map_status(row.get("Etat"))
            severity = map_severity(priority_code, priority_text)

            is_active = status not in {"resolved", "closed"}

            incidents.append(
                Incident(
                    ticket_number=ticket_number,
                    title=build_title(
                        ticket_number=ticket_number,
                        site_name=site_name,
                        priority_code=priority_code,
                        priority_text=priority_text,
                    ),
                    description=description,
                    source=clean_str(row.get("Mapping_Source"), "ml_synthetic_ticket"),
                    status=status,
                    severity=severity,
                    priority=priority_code,
                    problem_family=clean_str(row.get("Famille de problèmes")),
                    ticket_type=clean_str(row.get("Type ticket")),
                    site_name=site_name,
                    region_code=None,
                    technology="3G",
                    assigned_team=clean_str(row.get("EDS Pilote")),
                    started_at=started_at,
                    acknowledged_at=acknowledged_at,
                    resolved_at=resolved_at,
                    closed_at=closed_at,
                    is_active=is_active,
                    health_impact_score=impact_score_from_priority(
                        priority_code, priority_text
                    ),
                    root_cause_hint=root_cause_from_description(
                        description, priority_text
                    ),
                )
            )

        with transaction.atomic():
            if options["clear"]:
                self.stdout.write(self.style.WARNING("Clearing incident table..."))
                Incident.objects.all().delete()

            self.stdout.write("Importing incidents...")
            Incident.objects.bulk_create(incidents, batch_size=1000)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Unified ML incident dataset imported successfully."))
        self.stdout.write(f"Incident: {len(incidents)}")