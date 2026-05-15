from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd

from app.services.ml_service import DEFAULT_TARGET_COLUMN, load_training_dataframe


INCIDENT_SERVICE_BASE_URL = os.getenv(
    "INCIDENT_SERVICE_BASE_URL",
    "http://127.0.0.1:8002",
).rstrip("/")

KPI_SERVICE_BASE_URL = os.getenv(
    "KPI_SERVICE_BASE_URL",
    "http://127.0.0.1:8001",
).rstrip("/")


TARGET_COLUMNS = {
    DEFAULT_TARGET_COLUMN,
    "famille_de_problemes",
    "rca_family",
    "family",
    "label",
    "target",
}


def _http_get_json(url: str, authorization: Optional[str] = None, timeout: int = 8) -> Any:
    headers = {
        "Accept": "application/json",
    }

    if authorization:
        headers["Authorization"] = authorization

    request = Request(url, headers=headers, method="GET")

    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw)


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_json_value(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "item"):
        return value.item()

    return value


def _safe_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {key: _safe_json_value(value) for key, value in payload.items()}


def _extract_items(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        for key in ["results", "items", "data", "incidents", "sites"]:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        return [data]

    return []


def _field_matches(value: Any, query: str) -> bool:
    return query.lower() in _safe_str(value).lower()


def _incident_matches(incident: Dict[str, Any], ticket_number: str) -> bool:
    candidates = [
        incident.get("ticket_number"),
        incident.get("id"),
        incident.get("pk"),
        incident.get("ticket_id"),
        incident.get("reference"),
        incident.get("title"),
    ]

    ticket_clean = _safe_str(ticket_number)

    for value in candidates:
        if _safe_str(value) == ticket_clean:
            return True

    for value in candidates:
        if ticket_clean and ticket_clean.lower() in _safe_str(value).lower():
            return True

    return False


def fetch_incident_from_service(
    ticket_number: str,
    authorization: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    trace: List[str] = []

    encoded = quote(str(ticket_number))

    urls = [
        f"{INCIDENT_SERVICE_BASE_URL}/api/incidents/{encoded}/",
        f"{INCIDENT_SERVICE_BASE_URL}/api/incidents/?search={encoded}",
        f"{INCIDENT_SERVICE_BASE_URL}/api/incidents/?q={encoded}",
        f"{INCIDENT_SERVICE_BASE_URL}/api/incidents/",
    ]

    for url in urls:
        try:
            trace.append(f"Trying incident_service URL: {url}")
            data = _http_get_json(url, authorization=authorization)
            items = _extract_items(data)

            for item in items:
                if _incident_matches(item, ticket_number):
                    trace.append("Matched incident in incident_service.")
                    return item, trace

            if len(items) == 1 and _incident_matches(items[0], ticket_number):
                trace.append("Matched single incident response.")
                return items[0], trace

        except Exception as exc:
            trace.append(f"incident_service request failed: {url} | {exc}")

    trace.append("No incident match found in incident_service.")
    return None, trace


def extract_site_candidates(incident: Dict[str, Any], ticket_number: str) -> List[str]:
    raw_parts = [
        incident.get("site_name"),
        incident.get("site_id"),
        incident.get("nom_du_site"),
        incident.get("title"),
        incident.get("description"),
        incident.get("ticket_number"),
        ticket_number,
    ]

    text = " ".join(_safe_str(part) for part in raw_parts if _safe_str(part))

    patterns = [
        r"\b[A-Z]{2,5}_\d{3,5}_[A-Z0-9]{1,4}\b",
        r"\b[A-Z]{2,5}-\d{3,5}-[A-Z0-9]{1,5}\b",
        r"\b[A-Z]{2,5}_\d{3,5}\b",
        r"\b[A-Z]{2,5}-\d{3,5}\b",
    ]

    candidates: List[str] = []

    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            value = match.upper().strip()
            if value not in candidates:
                candidates.append(value)

    for field in ["site_name", "site_id", "nom_du_site"]:
        value = _safe_str(incident.get(field))
        if value and value.upper() not in candidates:
            candidates.append(value.upper())

    return candidates[:10]


def build_payload_from_incident(
    incident: Dict[str, Any],
    ticket_number: str,
) -> Dict[str, Any]:
    ticket_id = (
        incident.get("ticket_number")
        or incident.get("ticket_id")
        or ticket_number
    )

    title = _safe_str(incident.get("title"))
    description = _safe_str(incident.get("description"))
    status = _safe_str(incident.get("status"))
    severity = _safe_str(incident.get("severity"))
    priority = _safe_str(incident.get("priority"))
    technology = _safe_str(incident.get("technology"))
    problem_family = _safe_str(incident.get("problem_family"))
    ticket_type = _safe_str(incident.get("ticket_type"))
    root_cause_hint = _safe_str(incident.get("root_cause_hint"))

    text_parts = [
        title,
        description,
        f"Status: {status}" if status else "",
        f"Severity: {severity}" if severity else "",
        f"Priority: {priority}" if priority else "",
        f"Technology: {technology}" if technology else "",
        f"Problem family: {problem_family}" if problem_family else "",
        f"Ticket type: {ticket_type}" if ticket_type else "",
        f"Root cause hint: {root_cause_hint}" if root_cause_hint else "",
    ]

    ticket_text = ". ".join(part for part in text_parts if part)

    site_candidates = extract_site_candidates(incident, ticket_number)
    site_id = (
        incident.get("site_name")
        or incident.get("site_id")
        or incident.get("nom_du_site")
        or (site_candidates[0] if site_candidates else None)
    )

    region = incident.get("region_code")
    if not region and site_id:
        region = _safe_str(site_id).split("_")[0].split("-")[0]

    health_score = _safe_float(incident.get("health_impact_score"))

    payload = {
        "ticket_id": str(ticket_id),
        "ticket_text": ticket_text or f"Incident {ticket_id}",
        "site_id": site_id,
        "site_name": site_id,
        "nom_du_site": site_id,
        "region": region,
        "etat": status or None,
        "incident_status": status or None,
        "type_ticket": ticket_type or None,
        "priorite": priority or None,
        "priorite_texte": severity or None,
        "problem_family": problem_family or None,
        "technology": technology or None,
        "root_cause_hint": root_cause_hint or None,
    }

    if health_score is not None:
        payload["incident_potential"] = round(min(max(health_score / 100.0, 0.0), 1.0), 4)

    return _safe_payload(payload)


def _site_matches_item(site_item: Dict[str, Any], candidates: List[str]) -> bool:
    searchable_values = [
        site_item.get("site_id"),
        site_item.get("site_name"),
        site_item.get("nom_du_site"),
        site_item.get("nodeb_name"),
        site_item.get("name"),
        site_item.get("title"),
        site_item.get("code"),
    ]

    for candidate in candidates:
        candidate_clean = candidate.lower()

        for value in searchable_values:
            value_clean = _safe_str(value).lower()

            if not value_clean:
                continue

            if candidate_clean == value_clean:
                return True

            if candidate_clean in value_clean or value_clean in candidate_clean:
                return True

    return False


def fetch_kpi_context_from_service(
    site_candidates: List[str],
    authorization: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    trace: List[str] = []

    if not site_candidates:
        trace.append("No site candidates available for KPI lookup.")
        return None, trace

    urls: List[str] = []

    for candidate in site_candidates[:3]:
        encoded = quote(candidate)
        urls.extend(
            [
                f"{KPI_SERVICE_BASE_URL}/api/cartography/sites/?search={encoded}",
                f"{KPI_SERVICE_BASE_URL}/api/cartography/sites/?q={encoded}",
                f"{KPI_SERVICE_BASE_URL}/api/cartography/sites/",
            ]
        )

    seen_urls: List[str] = []

    for url in urls:
        if url in seen_urls:
            continue
        seen_urls.append(url)

        try:
            trace.append(f"Trying KPI service URL: {url}")
            data = _http_get_json(url, authorization=authorization)
            items = _extract_items(data)

            for item in items:
                if _site_matches_item(item, site_candidates):
                    trace.append("Matched KPI/site context in kpi_service.")
                    return item, trace

        except Exception as exc:
            trace.append(f"kpi_service request failed: {url} | {exc}")

    trace.append("No KPI/site match found in kpi_service.")
    return None, trace


def merge_kpi_context(payload: Dict[str, Any], kpi_item: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not kpi_item:
        return payload

    enriched = dict(payload)

    field_map = {
        "avg_cssr_ps": "kpi_3g_cssr_ps",
        "cssr_ps": "kpi_3g_cssr_ps",
        "kpi_3g_cssr_ps": "kpi_3g_cssr_ps",
        "avg_shosr": "kpi_3g_shosr",
        "shosr": "kpi_3g_shosr",
        "kpi_3g_shosr": "kpi_3g_shosr",
        "avg_throughput_3g": "kpi_3g_throughput",
        "throughput": "kpi_3g_throughput",
        "kpi_3g_throughput": "kpi_3g_throughput",
        "avg_drop_rate": "kpi_3g_dropcall_cs",
        "drop_rate": "kpi_3g_dropcall_cs",
        "kpi_3g_dropcall_cs": "kpi_3g_dropcall_cs",
        "avg_cs_rab_setup_sr": "kpi_3g_cs_rab_setup_sr",
        "kpi_3g_cs_rab_setup_sr": "kpi_3g_cs_rab_setup_sr",
        "avg_cs_interrat_ho_sr": "kpi_3g_cs_interrat_ho_sr",
        "kpi_3g_cs_interrat_ho_sr": "kpi_3g_cs_interrat_ho_sr",
    }

    for source_key, target_key in field_map.items():
        value = _safe_float(kpi_item.get(source_key))
        if value is not None:
            enriched[target_key] = value

    if not enriched.get("site_id"):
        enriched["site_id"] = (
            kpi_item.get("site_id")
            or kpi_item.get("nodeb_name")
            or kpi_item.get("site_name")
            or kpi_item.get("name")
        )

    if not enriched.get("site_name"):
        enriched["site_name"] = (
            kpi_item.get("site_name")
            or kpi_item.get("nodeb_name")
            or kpi_item.get("name")
            or enriched.get("site_id")
        )

    if not enriched.get("nom_du_site"):
        enriched["nom_du_site"] = enriched.get("site_name") or enriched.get("site_id")

    if not enriched.get("region"):
        enriched["region"] = kpi_item.get("region") or kpi_item.get("region_code")

    health_score = _safe_float(kpi_item.get("health_score"))
    if health_score is not None and "incident_potential" not in enriched:
        enriched["incident_potential"] = round(min(max(health_score / 100.0, 0.0), 1.0), 4)

    if kpi_item.get("status") and not enriched.get("incident_status"):
        enriched["incident_status"] = kpi_item.get("status")

    return _safe_payload(enriched)


def find_rca_dataset_context(
    ticket_number: str,
    site_candidates: List[str],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    trace: List[str] = []

    try:
        df = load_training_dataframe()
    except Exception as exc:
        trace.append(f"RCA dataset load failed: {exc}")
        return None, trace

    if df.empty:
        trace.append("RCA dataset is empty.")
        return None, trace

    matches = pd.DataFrame()

    if "ticket_id" in df.columns:
        matches = df.loc[df["ticket_id"].astype(str) == str(ticket_number)]

    if matches.empty and site_candidates:
        searchable_columns = [
            col
            for col in ["site_id", "nom_du_site", "site_name", "ticket_text"]
            if col in df.columns
        ]

        for candidate in site_candidates:
            mask = df[searchable_columns].astype(str).apply(
                lambda column: column.str.contains(candidate, case=False, na=False)
            ).any(axis=1)
            matches = df.loc[mask]

            if not matches.empty:
                break

    if matches.empty:
        trace.append("No RCA dataset match found.")
        return None, trace

    row = matches.iloc[0].copy()
    drop_columns = [col for col in TARGET_COLUMNS if col in row.index]

    payload = row.drop(labels=drop_columns, errors="ignore").to_dict()
    payload = _safe_payload(payload)

    payload["ticket_id"] = payload.get("ticket_id") or ticket_number
    payload["ticket_text"] = payload.get("ticket_text") or f"RCA dataset ticket {ticket_number}"
    payload["site_name"] = payload.get("site_name") or payload.get("nom_du_site") or payload.get("site_id")
    payload["nom_du_site"] = payload.get("nom_du_site") or payload.get("site_name") or payload.get("site_id")
    payload["region"] = payload.get("region") or _safe_str(payload.get("site_id")).split("_")[0]

    trace.append(f"Matched RCA dataset context using ticket/site. dataset_ticket_id={payload.get('ticket_id')}")
    return payload, trace


def build_backend_enriched_payload(
    ticket_number: str,
    authorization: Optional[str] = None,
) -> Dict[str, Any]:
    incident, incident_trace = fetch_incident_from_service(
        ticket_number=ticket_number,
        authorization=authorization,
    )

    if incident:
        payload = build_payload_from_incident(incident, ticket_number)
    else:
        payload = {
            "ticket_id": str(ticket_number),
            "ticket_text": f"Incident {ticket_number}",
        }

    site_candidates = extract_site_candidates(incident or payload, ticket_number)

    kpi_context, kpi_trace = fetch_kpi_context_from_service(
        site_candidates=site_candidates,
        authorization=authorization,
    )

    payload = merge_kpi_context(payload, kpi_context)

    dataset_context, dataset_trace = find_rca_dataset_context(
        ticket_number=ticket_number,
        site_candidates=site_candidates,
    )

    if dataset_context:
        # Dataset context enriches missing KPI fields without overwriting incident text identity.
        for key, value in dataset_context.items():
            if key not in payload or payload.get(key) in [None, ""]:
                payload[key] = value

        for kpi_key in [
            "kpi_3g_cssr_ps",
            "kpi_3g_shosr",
            "kpi_3g_throughput",
            "kpi_3g_dropcall_cs",
            "kpi_3g_cs_rab_setup_sr",
            "kpi_3g_cs_interrat_ho_sr",
            "incident_potential",
            "matched_incident_count",
            "incident_mapping_confidence",
            "worst_priority_code",
            "engineering_record_count",
            "frequency_band",
        ]:
            if dataset_context.get(kpi_key) is not None:
                payload[kpi_key] = dataset_context.get(kpi_key)

    payload["ticket_id"] = payload.get("ticket_id") or str(ticket_number)
    payload["ticket_text"] = payload.get("ticket_text") or f"Incident {ticket_number}"

    enrichment_trace = {
        "incident_service": incident_trace,
        "site_candidates": site_candidates,
        "kpi_service": kpi_trace,
        "rca_dataset": dataset_trace,
        "enrichment_result": {
            "incident_found": incident is not None,
            "kpi_context_found": kpi_context is not None,
            "rca_dataset_context_found": dataset_context is not None,
            "used_fallback_text_only": incident is None and kpi_context is None and dataset_context is None,
        },
    }

    return {
        "payload": _safe_payload(payload),
        "source_incident": incident,
        "kpi_context": kpi_context,
        "dataset_context": dataset_context,
        "enrichment_trace": enrichment_trace,
    }