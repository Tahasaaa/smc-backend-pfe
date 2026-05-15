from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    AnalyzeIncidentRequest,
    AnalyzeIncidentResponse,
    HypothesisItem,
    RCAApprovalRequest,
    RCAApprovalResponse,
    RCAReportGenerateRequest,
    RCAReportResponse,
    RunbookEntryResponse,
    RunbookPublishRequest,
    RunbookSearchResponse,
)
from app.services.ml_service import get_service
from app.services.persistence_service import (
    create_or_update_report,
    get_runbook_by_ticket_id,
    publish_runbook,
    search_runbooks,
    upsert_analysis,
    upsert_approval,
)
from app.services.report_service import (
    build_draft_report,
    build_kpi_insights,
    build_recommended_actions,
    build_recommended_checks,
)

router = APIRouter(prefix="/api/v2", tags=["RCA"])


@router.get("/test")
def test() -> Dict[str, str]:
    return {"message": "router works"}


@router.get("/model/info")
def model_info() -> Dict[str, Any]:
    service = get_service()

    if not service.is_trained or service.model is None:
        raise HTTPException(status_code=503, detail="Model artifacts are not loaded.")

    classes = []
    classifier = service.model.named_steps.get("classifier")
    if classifier is not None and hasattr(classifier, "classes_"):
        classes = classifier.classes_.tolist()

    return {
        "status": "ready",
        "classes": classes,
        "feature_count": len(service.training_feature_columns),
        "all_null_columns": service.all_null_columns,
        "text_column": service.text_column,
    }


@router.post("/analyze", response_model=AnalyzeIncidentResponse)
def analyze_incident(
    payload: AnalyzeIncidentRequest,
    db: Session = Depends(get_db),
) -> AnalyzeIncidentResponse:
    service = get_service()

    if not service.is_trained or service.model is None:
        raise HTTPException(status_code=503, detail="Model artifacts are not loaded.")

    try:
        payload_dict = payload.model_dump(exclude_none=True)
        top_k = payload_dict.pop("top_k", 3)

        result = service.predict(payload_dict, top_k=top_k)

        kpi_insights = build_kpi_insights(payload_dict)
        recommended_checks = build_recommended_checks(
            predicted_family=result["predicted_family"],
            payload=payload_dict,
            kpi_insights=kpi_insights,
        )
        recommended_actions = build_recommended_actions(
            predicted_family=result["predicted_family"],
            payload=payload_dict,
            kpi_insights=kpi_insights,
        )
        draft_report = build_draft_report(
            ticket_id=payload_dict.get("ticket_id") or "AUTO",
            predicted_family=result["predicted_family"],
            confidence=result["confidence"],
            top_hypotheses=result["top_hypotheses"],
            kpi_insights=kpi_insights,
            recommended_checks=recommended_checks,
            recommended_actions=recommended_actions,
            payload=payload_dict,
        )

        saved = upsert_analysis(
            db=db,
            payload=payload_dict,
            prediction=result,
            kpi_insights=kpi_insights,
            recommended_checks=recommended_checks,
            recommended_actions=recommended_actions,
            draft_report=draft_report,
        )

        return AnalyzeIncidentResponse(
            predicted_family=result["predicted_family"],
            confidence=result["confidence"],
            top_hypotheses=[HypothesisItem(**item) for item in result["top_hypotheses"]],
            ticket_id=saved.ticket_id,
            analysis_status=saved.status,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Analysis failed: {str(e)}")


@router.get("/tickets/{ticket_id}/analyze")
def analyze_existing_ticket(ticket_id: str, top_k: int = 3) -> Dict[str, Any]:
    service = get_service()

    if not service.is_trained or service.model is None:
        raise HTTPException(status_code=503, detail="Model artifacts are not loaded.")

    try:
        return service.predict_existing_ticket(ticket_id=ticket_id, top_k=top_k)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Analysis failed: {str(e)}")


@router.post("/approvals", response_model=RCAApprovalResponse)
def approve_rca(
    payload: RCAApprovalRequest,
    db: Session = Depends(get_db),
) -> RCAApprovalResponse:
    try:
        approval = upsert_approval(
            db=db,
            ticket_id=payload.ticket_id,
            approved_by=payload.approved_by,
            approval_status=payload.approval_status,
            approved_family=payload.approved_family,
            approved_checks=payload.approved_checks,
            approved_actions=payload.approved_actions,
            engineer_notes=payload.engineer_notes,
        )

        return RCAApprovalResponse(
            ticket_id=approval.ticket_id,
            approval_status=approval.approval_status,
            approved_family=approval.approved_family,
            approved_checks=approval.approved_checks_json or [],
            approved_actions=approval.approved_actions_json or [],
            engineer_notes=approval.engineer_notes,
            approved_by=approval.approved_by,
            approved_at=approval.approved_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Approval failed: {str(e)}")


@router.post("/reports", response_model=RCAReportResponse)
def generate_report(
    payload: RCAReportGenerateRequest,
    db: Session = Depends(get_db),
) -> RCAReportResponse:
    try:
        report = create_or_update_report(db=db, ticket_id=payload.ticket_id)

        return RCAReportResponse(
            ticket_id=report.ticket_id,
            report_id=report.report_id,
            report_status=report.report_status,
            report_text=report.report_text,
            generated_at=report.generated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Report generation failed: {str(e)}")


@router.post("/runbooks/publish", response_model=RunbookEntryResponse)
def publish_runbook_endpoint(
    payload: RunbookPublishRequest,
    db: Session = Depends(get_db),
) -> RunbookEntryResponse:
    try:
        runbook = publish_runbook(
            db=db,
            ticket_id=payload.ticket_id,
            created_by=payload.created_by,
            tags=payload.tags,
            is_reusable=payload.is_reusable,
        )

        return RunbookEntryResponse(
            ticket_id=runbook.ticket_id,
            site_id=runbook.site_id,
            site_name=runbook.site_name,
            region=runbook.region,
            approved_family=runbook.approved_family,
            incident_summary=runbook.incident_summary,
            final_conclusion=runbook.final_conclusion,
            checks=runbook.checks_json or [],
            actions=runbook.actions_json or [],
            engineer_notes=runbook.engineer_notes,
            report_id=runbook.report_id,
            tags=runbook.tags_json or [],
            is_reusable=runbook.is_reusable,
            created_by=runbook.created_by,
            created_at=runbook.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Runbook publish failed: {str(e)}")


# IMPORTANT: keep /search before /{ticket_id}
@router.get("/runbooks/search", response_model=RunbookSearchResponse)
def search_runbooks_endpoint(
    q: str | None = Query(default=None),
    approved_family: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> RunbookSearchResponse:
    items = search_runbooks(db=db, q=q, approved_family=approved_family, limit=limit)

    return RunbookSearchResponse(
        total=len(items),
        items=[
            RunbookEntryResponse(
                ticket_id=item.ticket_id,
                site_id=item.site_id,
                site_name=item.site_name,
                region=item.region,
                approved_family=item.approved_family,
                incident_summary=item.incident_summary,
                final_conclusion=item.final_conclusion,
                checks=item.checks_json or [],
                actions=item.actions_json or [],
                engineer_notes=item.engineer_notes,
                report_id=item.report_id,
                tags=item.tags_json or [],
                is_reusable=item.is_reusable,
                created_by=item.created_by,
                created_at=item.created_at,
            )
            for item in items
        ],
    )


@router.get("/runbooks/{ticket_id}", response_model=RunbookEntryResponse)
def get_runbook_endpoint(
    ticket_id: str,
    db: Session = Depends(get_db),
) -> RunbookEntryResponse:
    item = get_runbook_by_ticket_id(db=db, ticket_id=ticket_id)

    if item is None:
        raise HTTPException(status_code=404, detail=f"No runbook found for ticket_id='{ticket_id}'.")

    return RunbookEntryResponse(
        ticket_id=item.ticket_id,
        site_id=item.site_id,
        site_name=item.site_name,
        region=item.region,
        approved_family=item.approved_family,
        incident_summary=item.incident_summary,
        final_conclusion=item.final_conclusion,
        checks=item.checks_json or [],
        actions=item.actions_json or [],
        engineer_notes=item.engineer_notes,
        report_id=item.report_id,
        tags=item.tags_json or [],
        is_reusable=item.is_reusable,
        created_by=item.created_by,
        created_at=item.created_at,
    )