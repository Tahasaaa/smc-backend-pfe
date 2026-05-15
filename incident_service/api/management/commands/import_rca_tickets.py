from __future__ import annotations

import csv
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.models import Incident


DEFAULT_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "rca_service"
    / "data"
    / "tickets_radio_synthetic_linked.csv"
)

PRIORITY_TO_HEALTH_SCORE = {
    "P1": 90.0,
    "P2": 70.0,
    "P3": 45.0,
    "P4": 20.0,
}


def normalize_key(value: Any) -> str:
    text = str(value or "").strip().replace("\ufeff", "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default

    text = str(value).strip()

    if text.lower() in {"", "nan", "none", "null"}:
        return default

    return text


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        text = safe_str(value)
        if not text:
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def first_value(row: Dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = safe_str(row.get(normalize_key(key)))
        if value:
            return value

    return default


def detect_dialect(source: Path) -> csv.Dialect:
    with source.open("r", encoding="utf-8-sig", newline="") as file:
        sample = file.read(4096)

    try:
        return csv.Sniffer().sniff(sample, delimiters=",;|\t")
    except csv.Error:
        return csv.excel


def read_normalized_rows(source: Path) -> tuple[List[Dict[str, Any]], List[str]]:
    dialect = detect_dialect(source)

    rows: List[Dict[str, Any]] = []
    normalized_headers: List[str] = []

    with source.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, dialect=dialect)

        if reader.fieldnames:
            normalized_headers = [normalize_key(name) for name in reader.fieldnames]

        for raw_row in reader:
            row = {
                normalize_key(key): value
                for key, value in raw_row.items()
                if key is not None
            }
            rows.append(row)

    return rows, normalized_headers


def parse_datetime_safe(value: Any) -> datetime:
    text = safe_str(value)

    if not text:
        return timezone.now()

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            return timezone.make_aware(dt, timezone.get_current_timezone())
        except ValueError:
            continue

    return timezone.now()


def model_has_field(field_name: str) -> bool:
    return any(field.name == field_name for field in Incident._meta.fields)


def set_if_exists(payload: Dict[str, Any], field_name: str, value: Any) -> None:
    if model_has_field(field_name):
        payload[field_name] = value


def build_incident_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    ticket_number = first_value(
        row,
        "ticket_id",
        "ticket_number",
        "numero_ticket",
        "num_ticket",
        "id_ticket",
        "id",
        default="",
    )

    site_id = first_value(
        row,
        "site_id",
        "nom_du_site",
        "site_name",
        "nodeb_name",
        "site",
        default="",
    )

    ticket_text = first_value(
        row,
        "ticket_text",
        "description",
        "titre",
        "title",
        "libelle",
        default=f"Incident RCA synthetic ticket {ticket_number}",
    )

    family = first_value(
        row,
        "famille_de_problemes",
        "famille_problemes",
        "problem_family",
        "family",
        "rca_family",
        default="RCA under analysis",
    )

    priority = first_value(
        row,
        "priorite",
        "priority",
        "priority_code",
        default="P4",
    ).upper()

    severity = first_value(
        row,
        "priorite_texte",
        "priority_text",
        "severity",
        default=priority,
    )

    status = first_value(
        row,
        "etat",
        "status",
        "incident_status",
        default="in_progress",
    )

    region = first_value(
        row,
        "region",
        "region_code",
        default=site_id.split("_")[0].split("-")[0] if site_id else "",
    )

    technology = first_value(
        row,
        "technology",
        "technologie",
        "tech",
        default="3G",
    )

    incident_potential = safe_float(row.get(normalize_key("incident_potential")))

    if incident_potential is not None:
        if 0 <= incident_potential <= 1:
            health_score = round(incident_potential * 100.0, 2)
        else:
            health_score = round(min(max(incident_potential, 0.0), 100.0), 2)
    else:
        health_score = PRIORITY_TO_HEALTH_SCORE.get(priority, 20.0)

    title = ticket_text

    if site_id and site_id not in title:
        title = f"{site_id} - {ticket_text}"

    payload: Dict[str, Any] = {}

    set_if_exists(payload, "ticket_number", ticket_number)
    set_if_exists(payload, "title", title[:500])
    set_if_exists(payload, "description", ticket_text)
    set_if_exists(payload, "status", status)
    set_if_exists(payload, "severity", severity)
    set_if_exists(payload, "priority", priority)
    set_if_exists(payload, "problem_family", family)
    set_if_exists(payload, "site_name", site_id)
    set_if_exists(payload, "region_code", region[:50])
    set_if_exists(payload, "technology", technology)
    set_if_exists(payload, "started_at", parse_datetime_safe(row.get(normalize_key("date_debut"))))
    set_if_exists(
        payload,
        "is_active",
        status.lower() not in {"closed", "cloture", "cloture_", "clôturé", "resolved"},
    )
    set_if_exists(payload, "health_impact_score", health_score)
    set_if_exists(payload, "root_cause_hint", "Root cause under analysis")

    return payload


class Command(BaseCommand):
    help = "Import RCA synthetic tickets into incident_service Incident table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=str(DEFAULT_SOURCE),
            help="Path to tickets_radio_synthetic_linked.csv",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit number of imported rows. 0 means all rows.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview import without saving.",
        )
        parser.add_argument(
            "--prefix",
            default="",
            help="Optional prefix for ticket_number, example RCA-",
        )

    def handle(self, *args, **options):
        source = Path(options["source"])
        limit = int(options["limit"] or 0)
        dry_run = bool(options["dry_run"])
        prefix = safe_str(options.get("prefix"))

        if not source.exists():
            raise FileNotFoundError(f"CSV file not found: {source}")

        rows, headers = read_normalized_rows(source)

        created = 0
        updated = 0
        skipped = 0
        preview_items = []

        for index, row in enumerate(rows, start=1):
            if limit and index > limit:
                break

            payload = build_incident_payload(row)
            ticket_number = safe_str(payload.get("ticket_number"))

            if not ticket_number:
                skipped += 1
                continue

            if prefix and not ticket_number.startswith(prefix):
                ticket_number = f"{prefix}{ticket_number}"
                payload["ticket_number"] = ticket_number

            preview_items.append(
                {
                    "ticket_number": ticket_number,
                    "title": payload.get("title"),
                    "site_name": payload.get("site_name"),
                    "priority": payload.get("priority"),
                    "severity": payload.get("severity"),
                    "problem_family": payload.get("problem_family"),
                }
            )

            if dry_run:
                continue

            existing = Incident.objects.filter(ticket_number=ticket_number).first()

            if existing:
                for field_name, value in payload.items():
                    if field_name != "ticket_number":
                        setattr(existing, field_name, value)
                existing.save()
                updated += 1
            else:
                Incident.objects.create(**payload)
                created += 1

        self.stdout.write(self.style.SUCCESS("RCA synthetic incident import completed."))
        self.stdout.write(f"source: {source}")
        self.stdout.write(f"detected_headers: {headers[:30]}")
        self.stdout.write(f"dry_run: {dry_run}")
        self.stdout.write(f"created: {created}")
        self.stdout.write(f"updated: {updated}")
        self.stdout.write(f"skipped: {skipped}")
        self.stdout.write(f"preview_count: {len(preview_items)}")

        for item in preview_items[:10]:
            self.stdout.write(str(item))