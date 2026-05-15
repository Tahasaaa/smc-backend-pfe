from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import HypothesisItem
from app.services.backend_enrichment_service import build_backend_enriched_payload
from app.services.ml_service import get_service
from app.services.persistence_service import upsert_analysis
from app.services.rca_enrichment_service import build_enriched_rca_payload
from app.services.report_service import (
    build_draft_report,
    build_kpi_insights,
    build_recommended_actions,
    build_recommended_checks,
)


router = APIRouter(prefix="/api/v2/backend", tags=["Backend Integration"])


def _safe_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback

    if isinstance(value, str):
        return value

    if isinstance(value, (int, float, bool)):
        return str(value)

    return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _build_incident_context(enrichment: Dict[str, Any]) -> Dict[str, Any]:
    payload = enrichment.get("payload") or {}
    source_incident = enrichment.get("source_incident") or {}
    kpi_context = enrichment.get("kpi_context") or {}
    dataset_context = enrichment.get("dataset_context") or {}

    ticket_id = (
        payload.get("ticket_id")
        or source_incident.get("ticket_number")
        or dataset_context.get("ticket_id")
    )

    problem_statement = (
        payload.get("ticket_text")
        or source_incident.get("title")
        or source_incident.get("description")
        or dataset_context.get("ticket_text")
        or f"Incident {ticket_id}"
    )

    site_id = (
        payload.get("site_id")
        or payload.get("site_name")
        or payload.get("nom_du_site")
        or source_incident.get("site_name")
        or kpi_context.get("nodeb_name")
        or dataset_context.get("site_id")
        or dataset_context.get("site_name")
        or dataset_context.get("nom_du_site")
    )

    region = (
        payload.get("region")
        or source_incident.get("region_code")
        or dataset_context.get("region")
        or (_safe_text(site_id).split("_")[0] if site_id else None)
    )

    priority = (
        payload.get("priorite")
        or source_incident.get("priority")
        or dataset_context.get("priorite")
    )

    severity = (
        payload.get("priorite_texte")
        or source_incident.get("severity")
        or dataset_context.get("priorite_texte")
    )

    status = (
        payload.get("incident_status")
        or payload.get("etat")
        or source_incident.get("status")
        or dataset_context.get("etat")
    )

    technology = (
        payload.get("technology")
        or source_incident.get("technology")
        or dataset_context.get("technology")
        or "3G"
    )

    impact = (
        payload.get("incident_potential")
        or source_incident.get("health_impact_score")
        or dataset_context.get("incident_potential")
    )

    return {
        "ticket_id": ticket_id,
        "problem_statement": _safe_text(problem_statement, f"Incident {ticket_id}"),
        "site_id": site_id,
        "site_name": site_id,
        "region": region,
        "priority": priority,
        "severity": severity,
        "status": status,
        "technology": technology,
        "impact": impact,
        "problem_family_hint": (
            payload.get("problem_family")
            or source_incident.get("problem_family")
            or dataset_context.get("famille_de_problemes")
        ),
        "source_flags": {
            "incident_found": bool(enrichment.get("source_incident")),
            "kpi_context_found": bool(enrichment.get("kpi_context")),
            "dataset_context_found": bool(enrichment.get("dataset_context")),
        },
    }


def _build_hypothesis_reviews(
    result: Dict[str, Any],
    payload: Dict[str, Any],
    kpi_insights: list[str],
) -> list[Dict[str, Any]]:
    reviews: list[Dict[str, Any]] = []

    for index, item in enumerate(result.get("top_hypotheses", []), start=1):
        family = item.get("family")
        probability = _safe_float(item.get("probability"))

        if not family:
            continue

        suggested_checks = build_recommended_checks(
            predicted_family=family,
            payload=payload,
            kpi_insights=kpi_insights,
        )

        suggested_actions = build_recommended_actions(
            predicted_family=family,
            payload=payload,
            kpi_insights=kpi_insights,
        )

        reviews.append(
            {
                "rank": index,
                "family": family,
                "probability": probability,
                "probability_percent": round(probability * 100.0, 2),
                "is_model_choice": family == result.get("predicted_family"),
                "suggested_checks": suggested_checks,
                "suggested_actions": suggested_actions,
                "review_options": [
                    "validate",
                    "reject",
                    "partially_correct",
                ],
                "engineer_decision": None,
                "engineer_note": "",
            }
        )

    return reviews


def _build_response(
    saved,
    result: Dict[str, Any],
    kpi_insights: list[str],
    recommended_checks: list[str],
    recommended_actions: list[str],
    draft_report: str,
    enriched: Dict[str, Any],
    enrichment: Dict[str, Any],
) -> Dict[str, Any]:
    payload = enrichment.get("payload") or {}

    hypothesis_reviews = _build_hypothesis_reviews(
        result=result,
        payload=payload,
        kpi_insights=kpi_insights,
    )

    return {
        "predicted_family": result["predicted_family"],
        "confidence": result["confidence"],
        "top_hypotheses": [
            HypothesisItem(**item).model_dump()
            for item in result["top_hypotheses"]
        ],
        "ticket_id": saved.ticket_id,
        "analysis_status": saved.status,

        # Frontend-ready incident context
        "incident_context": _build_incident_context(enrichment),

        # Full raw contexts for debugging/details
        "payload": enrichment.get("payload"),
        "source_incident": enrichment.get("source_incident"),
        "kpi_context": enrichment.get("kpi_context"),
        "dataset_context": enrichment.get("dataset_context"),

        # RCA content
        "kpi_insights": kpi_insights,
        "recommended_checks": recommended_checks,
        "recommended_actions": recommended_actions,
        "draft_report": draft_report,
        "root_cause_summary": enriched["root_cause_summary"],
        "risk_if_not_fixed": enriched["risk_if_not_fixed"],
        "charts": enriched["charts"],

        # New: one card per hypothesis for frontend validation UI
        "hypothesis_reviews": hypothesis_reviews,

        # Status
        "explainability_status": {
            "lime": "available",
            "shap": "available",
            "note": "Local LIME text explanation and SHAP-style global explanation are available through /api/v2/explain endpoints.",
        },

        "enrichment_trace": enrichment["enrichment_trace"],
    }


@router.get("/incidents/{ticket_number}/preview")
def preview_backend_incident_enrichment(
    ticket_number: str,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    try:
        return build_backend_enriched_payload(
            ticket_number=ticket_number,
            authorization=authorization,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Backend incident enrichment preview failed: {str(e)}",
        )


@router.post("/incidents/{ticket_number}/analyze")
def analyze_backend_incident(
    ticket_number: str,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    service = get_service()

    if not service.is_trained or service.model is None:
        raise HTTPException(status_code=503, detail="Model artifacts are not loaded.")

    try:
        enrichment = build_backend_enriched_payload(
            ticket_number=ticket_number,
            authorization=authorization,
        )

        payload = enrichment["payload"]

        result = service.predict(payload, top_k=3)

        kpi_insights = build_kpi_insights(payload)

        recommended_checks = build_recommended_checks(
            predicted_family=result["predicted_family"],
            payload=payload,
            kpi_insights=kpi_insights,
        )

        recommended_actions = build_recommended_actions(
            predicted_family=result["predicted_family"],
            payload=payload,
            kpi_insights=kpi_insights,
        )

        draft_report = build_draft_report(
            ticket_id=payload.get("ticket_id") or ticket_number,
            predicted_family=result["predicted_family"],
            confidence=result["confidence"],
            top_hypotheses=result["top_hypotheses"],
            kpi_insights=kpi_insights,
            recommended_checks=recommended_checks,
            recommended_actions=recommended_actions,
            payload=payload,
        )

        enriched = build_enriched_rca_payload(
            predicted_family=result["predicted_family"],
            confidence=result["confidence"],
            top_hypotheses=result["top_hypotheses"],
            payload=payload,
            kpi_insights=kpi_insights,
        )

        saved = upsert_analysis(
            db=db,
            payload=payload,
            prediction=result,
            kpi_insights=kpi_insights,
            recommended_checks=recommended_checks,
            recommended_actions=recommended_actions,
            draft_report=draft_report,
        )

        return _build_response(
            saved=saved,
            result=result,
            kpi_insights=kpi_insights,
            recommended_checks=recommended_checks,
            recommended_actions=recommended_actions,
            draft_report=draft_report,
            enriched=enriched,
            enrichment=enrichment,
        )

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Backend incident analysis failed: {str(e)}",
        )