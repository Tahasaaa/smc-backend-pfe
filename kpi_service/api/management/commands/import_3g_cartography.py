import pandas as pd
from django.core.management.base import BaseCommand
from api.models import (
    Site3G,
    Cell3G,
    SiteKpiMap3G,
    RegionKpi3G,
    SiteOperationalView3G,
)


def nan_to_none(value):
    if pd.isna(value):
        return None
    return value


class Command(BaseCommand):
    help = "Import cleaned 3G cartography CSV files"

    def add_arguments(self, parser):
        parser.add_argument("--site3g", type=str, required=True)
        parser.add_argument("--cell3g", type=str, required=True)
        parser.add_argument("--sitekpi", type=str, required=True)
        parser.add_argument("--regionkpi", type=str, required=True)
        parser.add_argument("--siteop", type=str, required=True)

    def handle(self, *args, **options):
        site3g_path = options["site3g"]
        cell3g_path = options["cell3g"]
        sitekpi_path = options["sitekpi"]
        regionkpi_path = options["regionkpi"]
        siteop_path = options["siteop"]

        self.stdout.write("Loading CSV files...")

        site3g_df = pd.read_csv(site3g_path)
        cell3g_df = pd.read_csv(cell3g_path)
        sitekpi_df = pd.read_csv(sitekpi_path)
        regionkpi_df = pd.read_csv(regionkpi_path)
        siteop_df = pd.read_csv(siteop_path)

        # Parse dates safely
        for df in [sitekpi_df, regionkpi_df, siteop_df]:
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"], errors="coerce")

        # Remove invalid rows where required date is missing
        if "date" in sitekpi_df.columns:
            sitekpi_df = sitekpi_df.dropna(subset=["date"]).copy()

        if "date" in regionkpi_df.columns:
            regionkpi_df = regionkpi_df.dropna(subset=["date"]).copy()

        if "date" in siteop_df.columns:
            siteop_df = siteop_df.dropna(subset=["date"]).copy()

        self.stdout.write(f"site_3g rows: {len(site3g_df)}")
        self.stdout.write(f"cell_3g rows: {len(cell3g_df)}")
        self.stdout.write(f"site_kpi_map_3g rows after date cleaning: {len(sitekpi_df)}")
        self.stdout.write(f"region_kpi_3g rows after date cleaning: {len(regionkpi_df)}")
        self.stdout.write(f"site_operational_view_3g rows after date cleaning: {len(siteop_df)}")

        self.stdout.write("Clearing old tables...")
        Site3G.objects.all().delete()
        Cell3G.objects.all().delete()
        SiteKpiMap3G.objects.all().delete()
        RegionKpi3G.objects.all().delete()
        SiteOperationalView3G.objects.all().delete()

        self.stdout.write("Importing site_3g...")
        Site3G.objects.bulk_create([
            Site3G(
                nodeb_name=nan_to_none(row.get("nodeb_name")),
                nodeb_name_norm=nan_to_none(row.get("nodeb_name_norm")),
                nodeb_id=nan_to_none(row.get("nodeb_id")),
                rnc_name=nan_to_none(row.get("rnc_name")),
                latitude=nan_to_none(row.get("latitude")),
                longitude=nan_to_none(row.get("longitude")),
                cell_count=int(row.get("cell_count", 0)) if pd.notna(row.get("cell_count")) else 0,
                active=nan_to_none(row.get("active")),
            )
            for _, row in site3g_df.iterrows()
        ], batch_size=1000)

        self.stdout.write("Importing cell_3g...")
        Cell3G.objects.bulk_create([
            Cell3G(
                rnc_name=nan_to_none(row.get("rnc_name")),
                nodeb_name=nan_to_none(row.get("nodeb_name")),
                nodeb_name_norm=nan_to_none(row.get("nodeb_name_norm")),
                nodeb_id=nan_to_none(row.get("nodeb_id")),
                cell_name=nan_to_none(row.get("cell_name")),
                cell_name_norm=nan_to_none(row.get("cell_name_norm")),
                cell_id=nan_to_none(row.get("cell_id")),
                psc=nan_to_none(row.get("psc")),
                uarfcn_dl=nan_to_none(row.get("uarfcn_dl")),
                uarfcn_ul=nan_to_none(row.get("uarfcn_ul")),
                latitude=nan_to_none(row.get("latitude")),
                longitude=nan_to_none(row.get("longitude")),
                azimuth=nan_to_none(row.get("azimuth")),
                antenna_height=nan_to_none(row.get("antenna_height")),
                mech_tilt=nan_to_none(row.get("mech_tilt")),
                elec_tilt=nan_to_none(row.get("elec_tilt")),
                pilot_power=nan_to_none(row.get("pilot_power")),
                sector_id=nan_to_none(row.get("sector_id")),
                active=nan_to_none(row.get("active")),
            )
            for _, row in cell3g_df.iterrows()
        ], batch_size=1000)

        self.stdout.write("Importing site_kpi_map_3g...")
        SiteKpiMap3G.objects.bulk_create([
            SiteKpiMap3G(
                date=nan_to_none(row.get("date")),
                nodeb_name=nan_to_none(row.get("nodeb_name")),
                nodeb_name_norm=nan_to_none(row.get("nodeb_name_norm")),
                rnc_name=nan_to_none(row.get("rnc_name")),
                latitude=nan_to_none(row.get("latitude")),
                longitude=nan_to_none(row.get("longitude")),
                avg_cssr_ps=nan_to_none(row.get("avg_cssr_ps")),
                avg_ps_rab_sr=nan_to_none(row.get("avg_ps_rab_sr")),
                avg_throughput_3g=nan_to_none(row.get("avg_throughput_3g")),
                avg_iub_congestion=nan_to_none(row.get("avg_iub_congestion")),
                avg_drop_rate=nan_to_none(row.get("avg_drop_rate")),
                avg_availability_3g=nan_to_none(row.get("avg_availability_3g")),
                health_score=nan_to_none(row.get("health_score")),
                status=nan_to_none(row.get("status")),
            )
            for _, row in sitekpi_df.iterrows()
        ], batch_size=1000)

        self.stdout.write("Importing region_kpi_3g...")
        RegionKpi3G.objects.bulk_create([
            RegionKpi3G(
                date=nan_to_none(row.get("date")),
                rnc_name=nan_to_none(row.get("rnc_name")),
                site_count=int(row.get("site_count", 0)) if pd.notna(row.get("site_count")) else 0,
                avg_health_score=nan_to_none(row.get("avg_health_score")),
                avg_cssr_ps=nan_to_none(row.get("avg_cssr_ps")),
                avg_throughput_3g=nan_to_none(row.get("avg_throughput_3g")),
                avg_iub_congestion=nan_to_none(row.get("avg_iub_congestion")),
                good_sites=int(row.get("good_sites", 0)) if pd.notna(row.get("good_sites")) else 0,
                warning_sites=int(row.get("warning_sites", 0)) if pd.notna(row.get("warning_sites")) else 0,
                critical_sites=int(row.get("critical_sites", 0)) if pd.notna(row.get("critical_sites")) else 0,
            )
            for _, row in regionkpi_df.iterrows()
        ], batch_size=1000)

        self.stdout.write("Importing site_operational_view_3g...")
        SiteOperationalView3G.objects.bulk_create([
            SiteOperationalView3G(
                date=nan_to_none(row.get("date")),
                nodeb_name=nan_to_none(row.get("nodeb_name")),
                nodeb_name_norm=nan_to_none(row.get("nodeb_name_norm")),
                rnc_name=nan_to_none(row.get("rnc_name")),
                latitude=nan_to_none(row.get("latitude")),
                longitude=nan_to_none(row.get("longitude")),
                avg_cssr_ps=nan_to_none(row.get("avg_cssr_ps")),
                avg_ps_rab_sr=nan_to_none(row.get("avg_ps_rab_sr")),
                avg_throughput_3g=nan_to_none(row.get("avg_throughput_3g")),
                avg_iub_congestion=nan_to_none(row.get("avg_iub_congestion")),
                avg_drop_rate=nan_to_none(row.get("avg_drop_rate")),
                avg_availability_3g=nan_to_none(row.get("avg_availability_3g")),
                health_score=nan_to_none(row.get("health_score")),
                status=nan_to_none(row.get("status")),
                active_incident_count=int(row.get("active_incident_count", 0)) if pd.notna(row.get("active_incident_count")) else 0,
                critical_incident_count=int(row.get("critical_incident_count", 0)) if pd.notna(row.get("critical_incident_count")) else 0,
                last_incident_title=nan_to_none(row.get("last_incident_title")),
                main_kpi_issue=nan_to_none(row.get("main_kpi_issue")),
            )
            for _, row in siteop_df.iterrows()
        ], batch_size=1000)

        self.stdout.write(self.style.SUCCESS("3G cartography import completed successfully."))