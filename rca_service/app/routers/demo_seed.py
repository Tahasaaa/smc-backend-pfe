from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import RunbookEntry
from app.services.ml_service import DEFAULT_TARGET_COLUMN, get_service, load_training_dataframe
from app.services.persistence_service import (
    create_or_update_report,
    publish_runbook,
    upsert_analysis,
    upsert_approval,
)
from app.services.report_service import (
    build_draft_report,
    build_kpi_insights,
    build_recommended_actions,
    build_recommended_checks,
)


router = APIRouter(prefix="/api/v2/demo", tags=["Demo Seeding"])


RCA_FAMILIES = [
    "Performance",
    "Préventif",
    "Radio Access",
    "Transmission",
]

TARGET_COLUMNS = {
    DEFAULT_TARGET_COLUMN,
    "famille_de_problemes",
    "rca_family",
    "family",
    "label",
    "target",
}

KPI_COLUMNS = [
    "kpi_3g_cssr_ps",
    "kpi_3g_shosr",
    "kpi_3g_throughput",
    "kpi_3g_dropcall_cs",
    "kpi_3g_cs_rab_setup_sr",
    "kpi_3g_cs_interrat_ho_sr",
    "incident_potential",
    "matched_incident_count",
    "incident_mapping_confidence",
    "engineering_record_count",
]


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


def _current_runbook_counts(db: Session) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for family in RCA_FAMILIES:
        counts[family] = (
            db.query(RunbookEntry)
            .filter(RunbookEntry.approved_family == family)
            .count()
        )

    return counts


def _existing_ticket_ids(db: Session) -> set[str]:
    rows = db.query(RunbookEntry.ticket_id).all()
    return {str(row[0]) for row in rows if row[0] is not None}


def _family_tags(family: str) -> List[str]:
    base = ["balanced-demo", "rca-dataset", "auto-seeded"]

    if family == "Performance":
        return ["performance", "throughput", "optimization"] + base

    if family == "Préventif":
        return ["preventive", "early-warning", "monitoring"] + base

    if family == "Radio Access":
        return ["radio-access", "handover", "accessibility"] + base

    if family == "Transmission":
        return ["transmission", "backhaul", "transport"] + base

    return ["rca"] + base


def _build_payload_from_row(row: pd.Series, ticket_id: str) -> Dict[str, Any]:
    drop_columns = [col for col in TARGET_COLUMNS if col in row.index]

    payload = row.drop(labels=drop_columns, errors="ignore").to_dict()
    payload = _safe_payload(payload)

    payload["ticket_id"] = payload.get("ticket_id") or ticket_id
    payload["ticket_text"] = (
        payload.get("ticket_text")
        or payload.get("description")
        or f"RCA dataset ticket {ticket_id}"
    )

    payload["site_name"] = (
        payload.get("site_name")
        or payload.get("nom_du_site")
        or payload.get("site_id")
    )

    payload["nom_du_site"] = (
        payload.get("nom_du_site")
        or payload.get("site_name")
        or payload.get("site_id")
    )

    payload["region"] = payload.get("region") or str(
        payload.get("site_id") or ""
    ).split("_")[0]

    return payload


def _score_row_richness(row: pd.Series) -> int:
    score = 0

    for col in KPI_COLUMNS:
        if col in row.index and pd.notna(row.get(col)):
            score += 1

    if "ticket_text" in row.index and pd.notna(row.get("ticket_text")):
        score += 1

    if "site_id" in row.index and pd.notna(row.get("site_id")):
        score += 1

    return score


def _select_candidates(
    df: pd.DataFrame,
    family: str,
    needed: int,
    existing_ids: set[str],
) -> List[pd.Series]:
    if needed <= 0:
        return []

    if "famille_de_problemes" not in df.columns:
        raise ValueError("RCA dataframe does not contain famille_de_problemes.")

    if "ticket_id" not in df.columns:
        raise ValueError("RCA dataframe does not contain ticket_id.")

    family_df = df[
        df["famille_de_problemes"].astype(str).str.lower() == family.lower()
    ].copy()

    if family_df.empty:
        return []

    family_df["__richness_score"] = family_df.apply(_score_row_richness, axis=1)

    family_df = family_df.sort_values(
        by=["__richness_score", "ticket_id"],
        ascending=[False, True],
    )

    selected: List[pd.Series] = []

    for _, row in family_df.iterrows():
        ticket_id = str(row.get("ticket_id"))

        if ticket_id in existing_ids:
            continue

        selected.append(row)

        if len(selected) >= needed:
            break

    return selected


def _seed_one_ticket(
    db: Session,
    row: pd.Series,
    approved_family: str,
    created_by: str,
) -> Dict[str, Any]:
    service = get_service()

    if not service.is_trained or service.model is None:
        raise RuntimeError("Model artifacts are not loaded.")

    ticket_id = str(row.get("ticket_id"))
    payload = _build_payload_from_row(row=row, ticket_id=ticket_id)

    prediction = service.predict(payload, top_k=3)
    kpi_insights = build_kpi_insights(payload)

    recommended_checks = build_recommended_checks(
        predicted_family=approved_family,
        payload=payload,
        kpi_insights=kpi_insights,
    )

    recommended_actions = build_recommended_actions(
        predicted_family=approved_family,
        payload=payload,
        kpi_insights=kpi_insights,
    )

    draft_report = build_draft_report(
        ticket_id=ticket_id,
        predicted_family=prediction["predicted_family"],
        confidence=prediction["confidence"],
        top_hypotheses=prediction["top_hypotheses"],
        kpi_insights=kpi_insights,
        recommended_checks=recommended_checks,
        recommended_actions=recommended_actions,
        payload=payload,
    )

    analysis = upsert_analysis(
        db=db,
        payload=payload,
        prediction=prediction,
        kpi_insights=kpi_insights,
        recommended_checks=recommended_checks,
        recommended_actions=recommended_actions,
        draft_report=draft_report,
    )

    engineer_notes = (
        f"Seeded demo RCA runbook from labeled RCA dataset. "
        f"Approved family='{approved_family}'. "
        f"Model predicted='{prediction['predicted_family']}' "
        f"with confidence={prediction['confidence']}."
    )

    approval = upsert_approval(
        db=db,
        ticket_id=ticket_id,
        approved_by=created_by,
        approval_status="approved",
        approved_family=approved_family,
        approved_checks=recommended_checks,
        approved_actions=recommended_actions,
        engineer_notes=engineer_notes,
    )

    report = create_or_update_report(db=db, ticket_id=ticket_id)

    runbook = publish_runbook(
        db=db,
        ticket_id=ticket_id,
        created_by=created_by,
        tags=_family_tags(approved_family),
        is_reusable="yes",
    )

    return {
        "ticket_id": ticket_id,
        "site_id": analysis.site_id,
        "approved_family": approval.approved_family,
        "model_predicted_family": prediction["predicted_family"],
        "model_confidence": prediction["confidence"],
        "report_id": report.report_id,
        "runbook_created_at": runbook.created_at,
        "kpi_insights_count": len(kpi_insights),
        "status": "seeded",
    }


@router.get("/balance/status")
def demo_balance_status(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    counts = _current_runbook_counts(db)

    return {
        "status": "ok",
        "target_families": RCA_FAMILIES,
        "current_counts": counts,
        "total_runbooks": sum(counts.values()),
        "recommendation": "For a balanced demo, target at least 4 reusable runbooks per RCA family.",
    }


@router.post("/seed-balanced-runbooks")
def seed_balanced_runbooks(
    target_per_family: int = Query(default=4, ge=1, le=20),
    max_new: int = Query(default=20, ge=1, le=100),
    created_by: str = Query(default="taha"),
    dry_run: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        df = load_training_dataframe()
        existing_ids = _existing_ticket_ids(db)
        before_counts = _current_runbook_counts(db)

        plan: Dict[str, Any] = {}
        selected_by_family: Dict[str, List[pd.Series]] = {}

        total_planned_new = 0

        for family in RCA_FAMILIES:
            current_count = before_counts.get(family, 0)
            needed = max(0, target_per_family - current_count)

            if total_planned_new >= max_new:
                needed = 0
            elif total_planned_new + needed > max_new:
                needed = max_new - total_planned_new

            selected_rows = _select_candidates(
                df=df,
                family=family,
                needed=needed,
                existing_ids=existing_ids,
            )

            selected_by_family[family] = selected_rows
            total_planned_new += len(selected_rows)

            plan[family] = {
                "current_count": current_count,
                "target_count": target_per_family,
                "needed": needed,
                "selected": [
                    {
                        "ticket_id": str(row.get("ticket_id")),
                        "site_id": _safe_json_value(row.get("site_id")),
                        "ticket_text": _safe_json_value(row.get("ticket_text")),
                    }
                    for row in selected_rows
                ],
            }

        if dry_run:
            return {
                "status": "dry_run",
                "message": "No runbooks were created.",
                "target_per_family": target_per_family,
                "max_new": max_new,
                "before_counts": before_counts,
                "planned_new_total": total_planned_new,
                "plan": plan,
            }

        seeded: List[Dict[str, Any]] = []

        for family, rows in selected_by_family.items():
            for row in rows:
                result = _seed_one_ticket(
                    db=db,
                    row=row,
                    approved_family=family,
                    created_by=created_by,
                )
                seeded.append(result)

        after_counts = _current_runbook_counts(db)

        return {
            "status": "ok",
            "message": "Balanced demo runbook seeding completed.",
            "target_per_family": target_per_family,
            "before_counts": before_counts,
            "after_counts": after_counts,
            "seeded_total": len(seeded),
            "seeded_items": seeded,
            "note": (
                "These runbooks are created from labeled RCA dataset examples for demo and "
                "human-in-the-loop feedback testing. The production RCA model is not overwritten."
            ),
        }

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Balanced demo seeding failed: {str(e)}",
        )
