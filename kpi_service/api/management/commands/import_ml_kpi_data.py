import math
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.models import (
    Cell3G,
    RegionKpi3G,
    Site3G,
    SiteKpiMap3G,
    SiteOperationalView3G,
)


def clean_str(value, default=""):
    if value is None:
        return default

    if isinstance(value, float) and math.isnan(value):
        return default

    return str(value).strip()


def clean_float(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def clean_int(value, default=0):
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except Exception:
        return default


def normalize_name(value):
    return clean_str(value).upper().replace(" ", "").replace("-", "_")


def safe_mean(series):
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.mean())


def first_non_empty(series):
    for value in series:
        text = clean_str(value)
        if text:
            return text
    return ""


def mode_or_empty(series):
    values = series.dropna().astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return ""
    return values.mode().iloc[0]


def clip(value, low=0.0, high=100.0):
    if value is None:
        return None
    return max(low, min(high, float(value)))


def score_positive(value, fallback=75.0):
    if value is None:
        return fallback
    return clip(value)


def score_throughput(value, fallback=70.0):
    if value is None:
        return fallback

    # Synthetic throughput is usually in kbps / user-like scale.
    # 1500 is treated as excellent for demo scoring.
    return clip((float(value) / 1500.0) * 100.0)


def score_drop_rate(value, fallback=80.0):
    if value is None:
        return fallback

    # Lower drop is better.
    # 0% drop => 100, 5% drop => 0.
    return clip(100.0 - (float(value) * 20.0))


def compute_health_score(row):
    cssr = clean_float(row.get("KPI_3G_CSSR_PS"))
    shosr = clean_float(row.get("KPI_3G_SHOSR"))
    throughput = clean_float(row.get("KPI_3G_Throughput"))
    drop = clean_float(row.get("KPI_3G_DropCall_CS"))
    rab = clean_float(row.get("KPI_3G_CS_RAB_Setup_SR"))
    interrat = clean_float(row.get("KPI_3G_CS_InterRAT_HO_SR"))

    scores = [
        score_positive(cssr) * 0.22,
        score_positive(shosr) * 0.16,
        score_throughput(throughput) * 0.16,
        score_drop_rate(drop) * 0.18,
        score_positive(rab) * 0.16,
        score_positive(interrat) * 0.12,
    ]

    return round(sum(scores), 2)


def compute_status(row, health_score):
    matched_incidents = clean_int(row.get("Matched_Incident_Count"), 0)
    priority_code = clean_str(row.get("worst_priority_code")).upper()

    if priority_code in {"P1", "P2"}:
        return "critical"

    if health_score < 70:
        return "critical"

    if priority_code == "P3":
        return "warning"

    if health_score < 85 or matched_incidents > 0:
        return "warning"

    return "good"


def compute_main_kpi_issue(row):
    candidates = []

    cssr = clean_float(row.get("KPI_3G_CSSR_PS"))
    shosr = clean_float(row.get("KPI_3G_SHOSR"))
    throughput = clean_float(row.get("KPI_3G_Throughput"))
    drop = clean_float(row.get("KPI_3G_DropCall_CS"))
    rab = clean_float(row.get("KPI_3G_CS_RAB_Setup_SR"))
    interrat = clean_float(row.get("KPI_3G_CS_InterRAT_HO_SR"))

    if cssr is not None:
        candidates.append(("CSSR PS", max(0.0, 98.0 - cssr)))
    if shosr is not None:
        candidates.append(("SHOSR", max(0.0, 98.0 - shosr)))
    if throughput is not None:
        candidates.append(("Throughput 3G", max(0.0, 900.0 - throughput) / 10.0))
    if drop is not None:
        candidates.append(("Drop Call CS", max(0.0, drop - 1.0) * 10.0))
    if rab is not None:
        candidates.append(("CS RAB Setup SR", max(0.0, 98.0 - rab)))
    if interrat is not None:
        candidates.append(("CS InterRAT HO SR", max(0.0, 95.0 - interrat)))

    if not candidates:
        return "No KPI issue detected"

    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[0][0]


def priority_is_critical(priority_code, priority_text):
    priority_code = clean_str(priority_code).upper()
    priority_text = clean_str(priority_text).lower()

    return priority_code in {"P1", "P2"} or "critique" in priority_text


class Command(BaseCommand):
    help = "Import unified ML KPI/site dataset into KPI operational tables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--master",
            default="data_import/master_sites_corrected_synthetic.csv",
            help="Path to master sites CSV.",
        )
        parser.add_argument(
            "--engineering",
            default="data_import/engineering_parameters_corrected_synthetic.csv",
            help="Path to engineering parameters CSV.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing managed KPI operational tables before import.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate CSVs and print counts without writing to DB.",
        )

    def handle(self, *args, **options):
        base_dir = Path.cwd()

        master_path = Path(options["master"])
        engineering_path = Path(options["engineering"])

        if not master_path.is_absolute():
            master_path = base_dir / master_path

        if not engineering_path.is_absolute():
            engineering_path = base_dir / engineering_path

        if not master_path.exists():
            raise FileNotFoundError(f"Master CSV not found: {master_path}")

        if not engineering_path.exists():
            raise FileNotFoundError(f"Engineering CSV not found: {engineering_path}")

        self.stdout.write(self.style.NOTICE(f"Reading master CSV: {master_path}"))
        master_df = pd.read_csv(master_path)

        self.stdout.write(
            self.style.NOTICE(f"Reading engineering CSV: {engineering_path}")
        )
        engineering_df = pd.read_csv(engineering_path)

        master_df["site_id"] = master_df["site_id"].astype(str).str.strip()
        engineering_df["site_id"] = engineering_df["site_id"].astype(str).str.strip()

        site_groups = engineering_df.groupby("site_id", dropna=False)

        rnc_by_site = site_groups["RNCName"].agg(mode_or_empty).to_dict()
        nodeb_id_by_site = site_groups["NodeBID"].agg(first_non_empty).to_dict()
        cell_count_by_site = site_groups["CellName"].count().to_dict()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("CSV validation OK"))
        self.stdout.write(f"Master sites rows: {len(master_df)}")
        self.stdout.write(f"Engineering rows: {len(engineering_df)}")
        self.stdout.write(f"Unique engineering sites: {engineering_df['site_id'].nunique()}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry-run mode: no DB changes applied."))
            return

        now = timezone.now()

        site_objects = []
        cell_objects = []
        map_objects = []
        operational_objects = []

        for _, row in master_df.iterrows():
            site_id = clean_str(row.get("site_id")) or clean_str(row.get("Site_Name"))
            site_name = clean_str(row.get("Site_Name")) or site_id
            nodeb_name_norm = normalize_name(site_name)

            rnc_name = rnc_by_site.get(site_id, "")
            nodeb_id = clean_float(nodeb_id_by_site.get(site_id))
            cell_count = clean_int(cell_count_by_site.get(site_id), 0)

            latitude = clean_float(row.get("Latitude"))
            longitude = clean_float(row.get("Longitude"))
            active = clean_str(row.get("Active"), "UNKNOWN")

            health_score = compute_health_score(row)
            status = compute_status(row, health_score)
            main_kpi_issue = compute_main_kpi_issue(row)

            matched_incidents = clean_int(row.get("Matched_Incident_Count"), 0)
            priority_code = clean_str(row.get("worst_priority_code"))
            priority_text = clean_str(row.get("worst_priority_text"))

            critical_count = (
                matched_incidents if priority_is_critical(priority_code, priority_text) else 0
            )

            site_objects.append(
                Site3G(
                    nodeb_name=site_name,
                    nodeb_name_norm=nodeb_name_norm,
                    nodeb_id=nodeb_id,
                    rnc_name=rnc_name,
                    latitude=latitude,
                    longitude=longitude,
                    cell_count=cell_count,
                    active=active,
                )
            )

            map_objects.append(
                SiteKpiMap3G(
                    date=now,
                    nodeb_name=site_name,
                    nodeb_name_norm=nodeb_name_norm,
                    rnc_name=rnc_name,
                    latitude=latitude,
                    longitude=longitude,
                    avg_cssr_ps=clean_float(row.get("KPI_3G_CSSR_PS")),
                    avg_ps_rab_sr=clean_float(row.get("KPI_3G_CS_RAB_Setup_SR")),
                    avg_throughput_3g=clean_float(row.get("KPI_3G_Throughput")),
                    avg_iub_congestion=None,
                    avg_drop_rate=clean_float(row.get("KPI_3G_DropCall_CS")),
                    avg_availability_3g=None,
                    health_score=health_score,
                    status=status,
                )
            )

            operational_objects.append(
                SiteOperationalView3G(
                    date=now,
                    nodeb_name=site_name,
                    nodeb_name_norm=nodeb_name_norm,
                    rnc_name=rnc_name,
                    latitude=latitude,
                    longitude=longitude,
                    avg_cssr_ps=clean_float(row.get("KPI_3G_CSSR_PS")),
                    avg_ps_rab_sr=clean_float(row.get("KPI_3G_CS_RAB_Setup_SR")),
                    avg_throughput_3g=clean_float(row.get("KPI_3G_Throughput")),
                    avg_iub_congestion=None,
                    avg_drop_rate=clean_float(row.get("KPI_3G_DropCall_CS")),
                    avg_availability_3g=None,
                    health_score=health_score,
                    status=status,
                    active_incident_count=matched_incidents,
                    critical_incident_count=critical_count,
                    last_incident_title=(
                        f"{priority_code} - {priority_text}" if priority_code else ""
                    ),
                    main_kpi_issue=main_kpi_issue,
                )
            )

        for _, row in engineering_df.iterrows():
            nodeb_name = clean_str(row.get("NodeBName")) or clean_str(row.get("site_id"))
            cell_name = clean_str(row.get("CellName"))

            if not nodeb_name or not cell_name:
                continue

            cell_objects.append(
                Cell3G(
                    rnc_name=clean_str(row.get("RNCName")),
                    nodeb_name=nodeb_name,
                    nodeb_name_norm=normalize_name(nodeb_name),
                    nodeb_id=clean_float(row.get("NodeBID")),
                    cell_name=cell_name,
                    cell_name_norm=normalize_name(cell_name),
                    cell_id=clean_float(row.get("CellID")),
                    psc=clean_float(row.get("PSC")),
                    uarfcn_dl=clean_float(row.get("UARFCNDownlink")),
                    uarfcn_ul=clean_float(row.get("UARFCNUplink")),
                    latitude=clean_float(row.get("Latitude")),
                    longitude=clean_float(row.get("Longitude")),
                    azimuth=clean_float(row.get("Azimuth")),
                    antenna_height=clean_float(row.get("AntHeight")),
                    mech_tilt=clean_float(row.get("MechTilt")),
                    elec_tilt=clean_float(row.get("ElecTilt")),
                    pilot_power=clean_float(row.get("Pilot Power")),
                    sector_id=clean_str(row.get("Sector ID")),
                    active=clean_str(row.get("Active")) or clean_str(row.get("Status")),
                )
            )

        region_objects = []
        region_df = pd.DataFrame(
            [
                {
                    "rnc_name": obj.rnc_name or "UNKNOWN",
                    "health_score": obj.health_score,
                    "cssr": obj.avg_cssr_ps,
                    "throughput": obj.avg_throughput_3g,
                    "iub": obj.avg_iub_congestion,
                    "status": obj.status,
                }
                for obj in map_objects
            ]
        )

        for rnc_name, group in region_df.groupby("rnc_name"):
            good_sites = int((group["status"] == "good").sum())
            warning_sites = int((group["status"] == "warning").sum())
            critical_sites = int((group["status"] == "critical").sum())

            region_objects.append(
                RegionKpi3G(
                    date=now,
                    rnc_name=rnc_name,
                    site_count=int(len(group)),
                    avg_health_score=safe_mean(group["health_score"]),
                    avg_cssr_ps=safe_mean(group["cssr"]),
                    avg_throughput_3g=safe_mean(group["throughput"]),
                    avg_iub_congestion=safe_mean(group["iub"]),
                    good_sites=good_sites,
                    warning_sites=warning_sites,
                    critical_sites=critical_sites,
                )
            )

        with transaction.atomic():
            if options["clear"]:
                self.stdout.write(self.style.WARNING("Clearing managed KPI tables..."))
                SiteOperationalView3G.objects.all().delete()
                RegionKpi3G.objects.all().delete()
                SiteKpiMap3G.objects.all().delete()
                Cell3G.objects.all().delete()
                Site3G.objects.all().delete()

            self.stdout.write("Importing Site3G...")
            Site3G.objects.bulk_create(site_objects, batch_size=1000)

            self.stdout.write("Importing Cell3G...")
            Cell3G.objects.bulk_create(cell_objects, batch_size=1000)

            self.stdout.write("Importing SiteKpiMap3G...")
            SiteKpiMap3G.objects.bulk_create(map_objects, batch_size=1000)

            self.stdout.write("Importing SiteOperationalView3G...")
            SiteOperationalView3G.objects.bulk_create(
                operational_objects, batch_size=1000
            )

            self.stdout.write("Importing RegionKpi3G...")
            RegionKpi3G.objects.bulk_create(region_objects, batch_size=1000)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Unified ML KPI dataset imported successfully."))
        self.stdout.write(f"Site3G: {len(site_objects)}")
        self.stdout.write(f"Cell3G: {len(cell_objects)}")
        self.stdout.write(f"SiteKpiMap3G: {len(map_objects)}")
        self.stdout.write(f"SiteOperationalView3G: {len(operational_objects)}")
        self.stdout.write(f"RegionKpi3G: {len(region_objects)}")