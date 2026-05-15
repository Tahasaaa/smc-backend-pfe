from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from app.services.explainability_service import (
    build_global_explanation,
    build_local_explanation,
    explainability_package_status,
)


router = APIRouter(prefix="/api/v2/explain", tags=["Explainability"])


@router.get("/status")
def explainability_status() -> Dict[str, Any]:
    return {
        "status": "ready",
        "package_status": explainability_package_status(),
        "available_methods": [
            "local_perturbation_lime_style",
            "global_linear_importance_shap_style",
        ],
        "notes": [
            "Local endpoint explains one ticket by feature perturbation, similar to LIME reasoning.",
            "Global endpoint explains the logistic regression model using coefficient-based feature importance.",
            "Library-based LIME/SHAP can be added later if packages are installed and validated.",
        ],
    }


@router.get("/local/{ticket_id}")
def explain_local_ticket(
    ticket_id: str,
    top_n: int = Query(default=10, ge=1, le=30),
) -> Dict[str, Any]:
    try:
        return build_local_explanation(ticket_id=ticket_id, top_n=top_n)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Local explanation failed: {str(e)}",
        )


@router.get("/global")
def explain_global_model(
    top_n: int = Query(default=25, ge=1, le=100),
) -> Dict[str, Any]:
    try:
        return build_global_explanation(top_n=top_n)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Global explanation failed: {str(e)}",
        )