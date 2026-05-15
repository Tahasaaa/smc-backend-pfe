from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import RunbookEntry
from app.services.online_training_service import (
    get_online_training_status,
    predict_with_online_model,
    update_online_model_from_feedback,
)


router = APIRouter(prefix="/api/v2/training", tags=["Training Feedback"])


def _safe_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _runbook_to_feedback_item(runbook: RunbookEntry) -> Dict[str, Any]:
    return {
        "ticket_id": runbook.ticket_id,
        "site_id": runbook.site_id,
        "site_name": runbook.site_name,
        "region": runbook.region,
        "approved_family": runbook.approved_family,
        "incident_summary": runbook.incident_summary,
        "final_conclusion": runbook.final_conclusion,
        "checks": _safe_list(runbook.checks_json),
        "actions": _safe_list(runbook.actions_json),
        "engineer_notes": runbook.engineer_notes,
        "report_id": runbook.report_id,
        "tags": _safe_list(runbook.tags_json),
        "is_reusable": runbook.is_reusable,
        "created_by": runbook.created_by,
        "created_at": runbook.created_at,
        "updated_at": runbook.updated_at,
    }


@router.get("/feedback")
def export_training_feedback(
    q: Optional[str] = Query(default=None),
    approved_family: Optional[str] = Query(default=None),
    reusable_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    query = db.query(RunbookEntry)

    if reusable_only:
        query = query.filter(RunbookEntry.is_reusable == "yes")

    if approved_family:
        query = query.filter(RunbookEntry.approved_family == approved_family)

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                RunbookEntry.ticket_id.ilike(like),
                RunbookEntry.site_id.ilike(like),
                RunbookEntry.site_name.ilike(like),
                RunbookEntry.region.ilike(like),
                RunbookEntry.approved_family.ilike(like),
                RunbookEntry.incident_summary.ilike(like),
                RunbookEntry.final_conclusion.ilike(like),
                RunbookEntry.engineer_notes.ilike(like),
            )
        )

    items = query.order_by(RunbookEntry.created_at.desc()).limit(limit).all()

    return {
        "total": len(items),
        "limit": limit,
        "reusable_only": reusable_only,
        "approved_family": approved_family,
        "query": q,
        "learning_strategy": {
            "current": "Human-approved RCA/runbook cases are exported as feedback data for future offline retraining.",
            "future": "True online incremental learning can be added later using SGDClassifier(log_loss) with partial_fit.",
        },
        "items": [_runbook_to_feedback_item(item) for item in items],
    }


@router.get("/feedback/summary")
def training_feedback_summary(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    runbooks = db.query(RunbookEntry).all()

    by_family: Dict[str, int] = {}
    reusable_count = 0

    for item in runbooks:
        family = item.approved_family or "Unknown"
        by_family[family] = by_family.get(family, 0) + 1

        if item.is_reusable == "yes":
            reusable_count += 1

    return {
        "total_runbooks": len(runbooks),
        "reusable_runbooks": reusable_count,
        "by_family": by_family,
        "learning_strategy": "Approved runbooks represent validated RCA feedback that can be reused for future retraining.",
    }


@router.get("/online/status")
def online_training_status() -> Dict[str, Any]:
    return get_online_training_status()


@router.post("/online/update")
def online_training_update(
    reusable_only: bool = Query(default=True),
    approved_family: Optional[str] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        return update_online_model_from_feedback(
            db=db,
            reusable_only=reusable_only,
            approved_family=approved_family,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Online training update failed: {str(e)}",
        )


@router.post("/online/predict")
def online_training_predict(
    payload: Dict[str, Any] = Body(...),
    top_k: int = Query(default=3, ge=1, le=5),
) -> Dict[str, Any]:
    try:
        return predict_with_online_model(payload=payload, top_k=top_k)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Online model prediction failed: {str(e)}",
        )