from django.db import models


# =========================
# EXISTING KPI MODELS
# =========================

class Governorate(models.Model):
    region_code = models.CharField(max_length=4, unique=True)
    name_fr = models.CharField(max_length=100)
    name_ar = models.CharField(max_length=100, null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = 'governorate'
        managed = False

    def __str__(self):
        return self.name_fr


class NetworkSite(models.Model):
    nodeb_name = models.CharField(max_length=100, unique=True)
    rnc = models.CharField(max_length=20, null=True)
    region_code = models.CharField(max_length=4, null=True)
    technology = models.CharField(max_length=5, default='3G')

    class Meta:
        db_table = 'network_site'
        managed = False

    def __str__(self):
        return self.nodeb_name


class KpiRecord(models.Model):
    date = models.DateField()
    nodeb_name = models.CharField(max_length=100, null=True)
    cell_id = models.CharField(max_length=20, null=True)
    cell_name = models.CharField(max_length=100, null=True)
    rnc = models.CharField(max_length=20, null=True)
    region_code = models.CharField(max_length=4, null=True)
    technology = models.CharField(max_length=5, default='3G')

    integrity = models.FloatField(null=True)
    availability_3g = models.FloatField(null=True)

    cdr_cs = models.FloatField(null=True)
    cssr_ps = models.FloatField(null=True)
    cs_inter_rat_ho_sr = models.FloatField(null=True)
    call_setup_sr_cs = models.FloatField(null=True)
    cs_rrc_setup_sr = models.FloatField(null=True)
    cs_rab_setup_sr = models.FloatField(null=True)
    call_drop_dch = models.FloatField(null=True)
    call_drop_pch = models.FloatField(null=True)
    evqi = models.FloatField(null=True)
    ul_evqi = models.FloatField(null=True)
    dl_evqi = models.FloatField(null=True)
    vqi_bad_rate = models.FloatField(null=True)
    vqi_excellent_rate = models.FloatField(null=True)

    shosr = models.FloatField(null=True)
    ps_rab_setup_sr = models.FloatField(null=True)
    ps_rab_congestion_ratio = models.FloatField(null=True)
    ps_inter_rat_ho_sr = models.FloatField(null=True)
    r99_call_setup_sr = models.FloatField(null=True)
    hsdpa_call_setup_sr = models.FloatField(null=True)
    hsupa_call_setup_sr = models.FloatField(null=True)
    hsdpa_rab_sr = models.FloatField(null=True)
    hsupa_rab_sr = models.FloatField(null=True)
    cdr_ps = models.FloatField(null=True)
    ps_r99_drop_ratio = models.FloatField(null=True)
    drop_rate_all_data = models.FloatField(null=True)

    throughput_3g = models.FloatField(null=True)
    hsdpa_tput_per_user = models.FloatField(null=True)
    hsupa_tput_per_user = models.FloatField(null=True)
    total_dl_gb = models.FloatField(null=True)
    total_ul_gb = models.FloatField(null=True)
    speech_traffic_erl = models.FloatField(null=True)
    total_traffic_dl_ul = models.FloatField(null=True)
    avg_hsdpa_users = models.FloatField(null=True)

    ce_congestion = models.FloatField(null=True)
    codes_congestion = models.FloatField(null=True)
    iub_congestion = models.FloatField(null=True)
    radio_congestion = models.FloatField(null=True)
    hsdpa_congested_rate = models.FloatField(null=True)
    ps_congestion_rate = models.FloatField(null=True)

    ho_3g_2g_voice = models.FloatField(null=True)
    ho_3g_2g_ps = models.FloatField(null=True)
    ho_3g_2g_hsdpa = models.FloatField(null=True)
    inter_freq_hho_sr = models.FloatField(null=True)
    sho_success_rate = models.FloatField(null=True)

    sho_avg_ecno = models.FloatField(null=True)
    mean_rtwp = models.FloatField(null=True)
    rrc_worse_rscp = models.FloatField(null=True)
    rrc_worse_ecno = models.FloatField(null=True)
    sho_worse_rscp = models.FloatField(null=True)
    sho_worse_ecno = models.FloatField(null=True)
    ul_amr_bler = models.FloatField(null=True)

    class Meta:
        db_table = 'kpi_record'
        managed = False

    def __str__(self):
        return f"{self.date} - {self.nodeb_name}"


# =========================
# NEW UPGRADE MODELS
# =========================

class Site3G(models.Model):
    nodeb_name = models.CharField(max_length=150)
    nodeb_name_norm = models.CharField(max_length=150, db_index=True)
    nodeb_id = models.FloatField(null=True, blank=True)
    rnc_name = models.CharField(max_length=100, null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    cell_count = models.IntegerField(default=0)
    active = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = 'site_3g'
        indexes = [
            models.Index(fields=['nodeb_name_norm']),
            models.Index(fields=['rnc_name']),
        ]

    def __str__(self):
        return self.nodeb_name


class Cell3G(models.Model):
    rnc_name = models.CharField(max_length=100, null=True, blank=True)
    nodeb_name = models.CharField(max_length=150)
    nodeb_name_norm = models.CharField(max_length=150, db_index=True)
    nodeb_id = models.FloatField(null=True, blank=True)

    cell_name = models.CharField(max_length=150)
    cell_name_norm = models.CharField(max_length=150, db_index=True)
    cell_id = models.FloatField(null=True, blank=True)

    psc = models.FloatField(null=True, blank=True)
    uarfcn_dl = models.FloatField(null=True, blank=True)
    uarfcn_ul = models.FloatField(null=True, blank=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    azimuth = models.FloatField(null=True, blank=True)

    antenna_height = models.FloatField(null=True, blank=True)
    mech_tilt = models.FloatField(null=True, blank=True)
    elec_tilt = models.FloatField(null=True, blank=True)
    pilot_power = models.FloatField(null=True, blank=True)

    sector_id = models.CharField(max_length=100, null=True, blank=True)
    active = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = 'cell_3g'
        indexes = [
            models.Index(fields=['nodeb_name_norm']),
            models.Index(fields=['cell_name_norm']),
        ]

    def __str__(self):
        return self.cell_name


class SiteKpiMap3G(models.Model):
    date = models.DateTimeField(db_index=True)
    nodeb_name = models.CharField(max_length=150)
    nodeb_name_norm = models.CharField(max_length=150, db_index=True)
    rnc_name = models.CharField(max_length=100, null=True, blank=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    avg_cssr_ps = models.FloatField(null=True, blank=True)
    avg_ps_rab_sr = models.FloatField(null=True, blank=True)
    avg_throughput_3g = models.FloatField(null=True, blank=True)
    avg_iub_congestion = models.FloatField(null=True, blank=True)
    avg_drop_rate = models.FloatField(null=True, blank=True)
    avg_availability_3g = models.FloatField(null=True, blank=True)

    health_score = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = 'site_kpi_map_3g'
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['nodeb_name_norm']),
            models.Index(fields=['status']),
            models.Index(fields=['rnc_name']),
        ]

    def __str__(self):
        return f"{self.nodeb_name} - {self.date}"


class RegionKpi3G(models.Model):
    date = models.DateTimeField(db_index=True)
    rnc_name = models.CharField(max_length=100, null=True, blank=True)

    site_count = models.IntegerField(default=0)
    avg_health_score = models.FloatField(null=True, blank=True)
    avg_cssr_ps = models.FloatField(null=True, blank=True)
    avg_throughput_3g = models.FloatField(null=True, blank=True)
    avg_iub_congestion = models.FloatField(null=True, blank=True)

    good_sites = models.IntegerField(default=0)
    warning_sites = models.IntegerField(default=0)
    critical_sites = models.IntegerField(default=0)

    class Meta:
        db_table = 'region_kpi_3g'
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['rnc_name']),
        ]

    def __str__(self):
        return f"{self.rnc_name} - {self.date}"


class SiteOperationalView3G(models.Model):
    date = models.DateTimeField(db_index=True)
    nodeb_name = models.CharField(max_length=150)
    nodeb_name_norm = models.CharField(max_length=150, db_index=True)
    rnc_name = models.CharField(max_length=100, null=True, blank=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    avg_cssr_ps = models.FloatField(null=True, blank=True)
    avg_ps_rab_sr = models.FloatField(null=True, blank=True)
    avg_throughput_3g = models.FloatField(null=True, blank=True)
    avg_iub_congestion = models.FloatField(null=True, blank=True)
    avg_drop_rate = models.FloatField(null=True, blank=True)
    avg_availability_3g = models.FloatField(null=True, blank=True)

    health_score = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=50, null=True, blank=True)

    active_incident_count = models.IntegerField(default=0)
    critical_incident_count = models.IntegerField(default=0)
    last_incident_title = models.TextField(null=True, blank=True)
    main_kpi_issue = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'site_operational_view_3g'
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['nodeb_name_norm']),
            models.Index(fields=['status']),
            models.Index(fields=['rnc_name']),
        ]

    def __str__(self):
        return f"{self.nodeb_name} - {self.date}"