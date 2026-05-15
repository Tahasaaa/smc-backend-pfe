from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: float) -> float:
    return round(float(value) * 100.0, 2)


def confidence_label(confidence: float) -> str:
    if confidence >= 0.90:
        return "very_high"
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.60:
        return "medium"
    return "low"


def build_root_cause_summary(
    predicted_family: str,
    confidence: float,
    payload: Dict[str, Any],
    kpi_insights: List[str],
) -> Dict[str, Any]:
    site_name = payload.get("site_name") or payload.get("nom_du_site") or "Unknown site"
    priority = payload.get("priorite_texte") or payload.get("priorite") or "Unknown priority"

    if predicted_family == "Transmission":
        root_cause = (
            "The most probable root cause is a transmission or backhaul degradation "
            "impacting service continuity and throughput stability."
        )
    elif predicted_family == "Radio Access":
        root_cause = (
            "The most probable root cause is a radio access degradation affecting "
            "accessibility, mobility, or sector-level service quality."
        )
    elif predicted_family == "Performance":
        root_cause = (
            "The most probable root cause is a performance degradation linked to "
            "traffic pressure, congestion, or optimization gaps."
        )
    elif predicted_family == "Préventif":
        root_cause = (
            "The case appears to be an early degradation pattern that should be handled "
            "preventively before it becomes a major incident."
        )
    else:
        root_cause = (
            "The root cause remains uncertain and requires additional engineer validation."
        )

    return {
        "site_name": site_name,
        "priority": priority,
        "predicted_family": predicted_family,
        "confidence": round(float(confidence), 4),
        "confidence_percent": _pct(confidence),
        "confidence_label": confidence_label(confidence),
        "root_cause": root_cause,
        "evidence_summary": (
            kpi_insights[:3]
            if kpi_insights
            else ["Limited KPI evidence was provided for this analysis."]
        ),
    }


def build_risk_if_not_fixed(
    predicted_family: str,
    confidence: float,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    incident_potential = _safe_float(payload.get("incident_potential")) or 0.0
    matched_count = _safe_float(payload.get("matched_incident_count")) or 0.0
    priority = str(payload.get("priorite") or "").upper()
    priority_text = str(payload.get("priorite_texte") or "").lower()

    base_score = 35.0

    if confidence >= 0.90:
        base_score += 20.0
    elif confidence >= 0.75:
        base_score += 14.0
    elif confidence >= 0.60:
        base_score += 8.0

    base_score += min(25.0, incident_potential * 25.0)
    base_score += min(15.0, matched_count * 3.0)

    if priority in {"P1", "P2"} or "critique" in priority_text or "élevée" in priority_text or "elevee" in priority_text:
        base_score += 15.0

    risk_score = max(0.0, min(100.0, base_score))

    if risk_score >= 85:
        risk_level = "critical"
        estimated_time_to_impact = "0-4 hours"
        escalation = "Immediate escalation is recommended."
    elif risk_score >= 70:
        risk_level = "high"
        estimated_time_to_impact = "4-12 hours"
        escalation = "Prioritize remediation during the current shift."
    elif risk_score >= 50:
        risk_level = "medium"
        estimated_time_to_impact = "12-24 hours"
        escalation = "Monitor closely and schedule corrective action."
    else:
        risk_level = "low"
        estimated_time_to_impact = "24-48 hours"
        escalation = "Continue observation and validate if symptoms persist."

    family_impact = {
        "Transmission": "Possible service instability, packet loss, throughput collapse, and cascading site degradation.",
        "Radio Access": "Possible access failures, dropped calls, mobility degradation, and user experience impact.",
        "Performance": "Possible congestion, slow throughput, poor user experience, and repeated complaints.",
        "Préventif": "Possible evolution from early warning pattern to operational incident if ignored.",
    }.get(
        predicted_family,
        "Possible operational degradation if the issue is not investigated.",
    )

    return {
        "risk_level": risk_level,
        "risk_score": round(risk_score, 2),
        "estimated_time_to_impact": estimated_time_to_impact,
        "impact_if_not_fixed": family_impact,
        "escalation_advice": escalation,
    }


def build_hypothesis_chart_data(top_hypotheses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "label": item.get("family", "Unknown"),
            "value": _pct(float(item.get("probability", 0.0))),
            "raw_probability": round(float(item.get("probability", 0.0)), 4),
        }
        for item in top_hypotheses
    ]


def build_kpi_evidence_chart_data(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    metrics = [
        {
            "label": "CSSR PS",
            "value": _safe_float(payload.get("kpi_3g_cssr_ps")),
            "threshold": 95.0,
            "direction": "low_is_bad",
        },
        {
            "label": "SHOSR",
            "value": _safe_float(payload.get("kpi_3g_shosr")),
            "threshold": 95.0,
            "direction": "low_is_bad",
        },
        {
            "label": "Throughput",
            "value": _safe_float(payload.get("kpi_3g_throughput")),
            "threshold": 4000.0,
            "direction": "low_is_bad",
        },
        {
            "label": "Drop Call CS",
            "value": _safe_float(payload.get("kpi_3g_dropcall_cs")),
            "threshold": 2.0,
            "direction": "high_is_bad",
        },
        {
            "label": "CS RAB Setup",
            "value": _safe_float(payload.get("kpi_3g_cs_rab_setup_sr")),
            "threshold": 95.0,
            "direction": "low_is_bad",
        },
        {
            "label": "InterRAT HO",
            "value": _safe_float(payload.get("kpi_3g_cs_interrat_ho_sr")),
            "threshold": 95.0,
            "direction": "low_is_bad",
        },
    ]

    chart = []

    for metric in metrics:
        value = metric["value"]
        threshold = metric["threshold"]

        if value is None:
            continue

        if metric["direction"] == "low_is_bad":
            if threshold <= 0:
                severity_score = 0.0
            else:
                severity_score = max(0.0, min(100.0, ((threshold - value) / threshold) * 100.0))
        else:
            if threshold <= 0:
                severity_score = 0.0
            else:
                severity_score = max(0.0, min(100.0, ((value - threshold) / threshold) * 100.0))

        chart.append(
            {
                "label": metric["label"],
                "value": round(value, 2),
                "threshold": threshold,
                "severity_score": round(severity_score, 2),
                "status": "degraded" if severity_score > 0 else "normal",
            }
        )

    return chart


def build_risk_timeline_chart_data(risk: Dict[str, Any]) -> List[Dict[str, Any]]:
    current = float(risk.get("risk_score", 0.0))

    return [
        {"label": "Now", "risk_score": round(current, 2)},
        {"label": "+4h", "risk_score": round(min(100.0, current + 8.0), 2)},
        {"label": "+12h", "risk_score": round(min(100.0, current + 16.0), 2)},
        {"label": "+24h", "risk_score": round(min(100.0, current + 25.0), 2)},
    ]


def build_chart_payload(
    top_hypotheses: List[Dict[str, Any]],
    payload: Dict[str, Any],
    risk: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "hypothesis_probability": build_hypothesis_chart_data(top_hypotheses),
        "kpi_evidence": build_kpi_evidence_chart_data(payload),
        "risk_timeline": build_risk_timeline_chart_data(risk),
    }


def build_enriched_rca_payload(
    predicted_family: str,
    confidence: float,
    top_hypotheses: List[Dict[str, Any]],
    payload: Dict[str, Any],
    kpi_insights: List[str],
) -> Dict[str, Any]:
    root_cause_summary = build_root_cause_summary(
        predicted_family=predicted_family,
        confidence=confidence,
        payload=payload,
        kpi_insights=kpi_insights,
    )

    risk = build_risk_if_not_fixed(
        predicted_family=predicted_family,
        confidence=confidence,
        payload=payload,
    )

    charts = build_chart_payload(
        top_hypotheses=top_hypotheses,
        payload=payload,
        risk=risk,
    )

    return {
        "root_cause_summary": root_cause_summary,
        "risk_if_not_fixed": risk,
        "charts": charts,
        "explainability_status": {
            "lime": "planned",
            "shap": "planned",
            "note": "Current response is model-probability and KPI-evidence based. LIME/SHAP will be added after the service is stable.",
        },
    }