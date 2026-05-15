from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    AnalyzeIncidentRequest,
    AnalyzeIncidentResponse,
    HypothesisItem,
    RCAAnalysisDetailResponse,
    RCAApprovalRequest,
    RCAApprovalResponse,
    RCAReportGenerateRequest,
    RCAReportResponse,
    RunbookEntryResponse,
    RunbookPublishRequest,
    RunbookSearchResponse,
)
from app.services.ml_service import get_service, load_training_dataframe
from app.services.persistence_service import (
    create_or_update_report,
    get_analysis_by_ticket_id,
    get_report_by_ticket_id,
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
from app.services.rca_enrichment_service import build_enriched_rca_payload


router = APIRouter(prefix="/api/v2", tags=["RCA"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

REQUIRED_ARTIFACTS = {
    "model": "model.pkl",
    "feature_columns": "feature_columns.json",
    "numeric_columns": "numeric_columns.json",
    "categorical_columns": "categorical_columns.json",
    "all_null_columns": "all_null_columns.json",
    "metadata": "model_metadata.json",
}


def _fix_mojibake_text(value: str) -> str:
    try:
        if "Ã" in value or "Â" in value:
            return value.encode("latin1").decode("utf-8")
    except UnicodeError:
        pass

    return value


def _normalize_text_recursively(value: Any) -> Any:
    if isinstance(value, str):
        return _fix_mojibake_text(value)

    if isinstance(value, list):
        return [_normalize_text_recursively(item) for item in value]

    if isinstance(value, dict):
        return {
            key: _normalize_text_recursively(item)
            for key, item in value.items()
        }

    return value


def _read_model_metadata() -> Dict[str, Any]:
    metadata_file = ARTIFACTS_DIR / "model_metadata.json"

    if not metadata_file.exists():
        return {}

    with metadata_file.open("r", encoding="utf-8") as file:
        metadata = json.load(file)

    return _normalize_text_recursively(metadata)


def _artifact_status() -> Dict[str, Any]:
    artifacts: Dict[str, Any] = {}

    for artifact_key, filename in REQUIRED_ARTIFACTS.items():
        path = ARTIFACTS_DIR / filename
        artifacts[artifact_key] = {
            "filename": filename,
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }

    return artifacts


def _to_json_safe_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    safe_payload: Dict[str, Any] = {}

    for key, value in payload.items():
        try:
            if pd.isna(value):
                safe_payload[key] = None
                continue
        except (TypeError, ValueError):
            pass

        if hasattr(value, "item"):
            safe_payload[key] = value.item()
        else:
            safe_payload[key] = value

    return safe_payload


def _build_analysis_response(
    saved,
    result: Dict[str, Any],
    kpi_insights: list[str],
    recommended_checks: list[str],
    recommended_actions: list[str],
    draft_report: str,
    enriched: Dict[str, Any],
) -> AnalyzeIncidentResponse:
    return AnalyzeIncidentResponse(
        predicted_family=result["predicted_family"],
        confidence=result["confidence"],
        top_hypotheses=[
            HypothesisItem(**item) for item in result["top_hypotheses"]
        ],
        ticket_id=saved.ticket_id,
        analysis_status=saved.status,
        kpi_insights=kpi_insights,
        recommended_checks=recommended_checks,
        recommended_actions=recommended_actions,
        draft_report=draft_report,
        root_cause_summary=enriched["root_cause_summary"],
        risk_if_not_fixed=enriched["risk_if_not_fixed"],
        charts=enriched["charts"],
        explainability_status=enriched["explainability_status"],
    )


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

    metadata = _read_model_metadata()
    artifact_status = _artifact_status()

    return {
        "status": "ready",
        "model_name": metadata.get("model_name", "v2_rca_model"),
        "model_version": metadata.get("model_version"),
        "trained_at_utc": metadata.get("trained_at_utc"),
        "target_column": metadata.get("target_column", service.target_column),
        "rows": metadata.get("rows"),
        "classes": metadata.get("classes") or classes,
        "runtime_classes": classes,
        "feature_count": metadata.get(
            "feature_count",
            len(service.training_feature_columns),
        ),
        "numeric_feature_count": metadata.get(
            "numeric_feature_count",
            len(service.numeric_columns),
        ),
        "categorical_feature_count": metadata.get(
            "categorical_feature_count",
            len(service.categorical_columns),
        ),
        "text_column": metadata.get("text_column", service.text_column),
        "all_null_columns": metadata.get(
            "all_null_columns",
            service.all_null_columns,
        ),
        "data_sources": metadata.get("data", {}).get("sources", []),
        "artifact_status": artifact_status,
        "training_notes": metadata.get("notes", []),
    }


@router.get("/dataset/tickets")
def list_dataset_tickets(
    q: str | None = Query(default=None),
    family: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> Dict[str, Any]:
    try:
        df = load_training_dataframe()

        if family and "famille_de_problemes" in df.columns:
            df = df[
                df["famille_de_problemes"].astype(str).str.lower()
                == family.lower()
            ]

        if priority and "priorite" in df.columns:
            df = df[df["priorite"].astype(str).str.upper() == priority.upper()]

        if q:
            q_lower = q.lower()
            searchable_columns = [
                "ticket_id",
                "site_id",
                "ticket_text",
                "nom_du_site",
                "famille_de_problemes",
                "priorite",
                "priorite_texte",
            ]
            existing_columns = [
                col for col in searchable_columns if col in df.columns
            ]

            if existing_columns:
                mask = df[existing_columns].astype(str).apply(
                    lambda col: col.str.lower().str.contains(q_lower, na=False)
                ).any(axis=1)
                df = df[mask]

        total = int(len(df))
        df = df.head(limit)

        items = []

        for _, row in df.iterrows():
            raw_item = {
                "ticket_id": row.get("ticket_id"),
                "site_id": row.get("site_id"),
                "site_name": row.get("nom_du_site") or row.get("site_name"),
                "region": row.get("region"),
                "ticket_text": row.get("ticket_text"),
                "family": row.get("famille_de_problemes"),
                "priority": row.get("priorite"),
                "priority_text": row.get("priorite_texte"),
                "incident_potential": row.get("incident_potential"),
                "matched_incident_count": row.get("matched_incident_count"),
                "kpi_3g_cssr_ps": row.get("kpi_3g_cssr_ps"),
                "kpi_3g_throughput": row.get("kpi_3g_throughput"),
                "kpi_3g_dropcall_cs": row.get("kpi_3g_dropcall_cs"),
                "kpi_3g_cs_interrat_ho_sr": row.get(
                    "kpi_3g_cs_interrat_ho_sr"
                ),
            }

            items.append(_to_json_safe_payload(raw_item))

        return {
            "total": total,
            "limit": limit,
            "items": items,
        }

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Dataset ticket listing failed: {str(e)}",
        )


@router.get("/analyses/{ticket_id}", response_model=RCAAnalysisDetailResponse)
def get_analysis_endpoint(
    ticket_id: str,
    db: Session = Depends(get_db),
) -> RCAAnalysisDetailResponse:
    analysis = get_analysis_by_ticket_id(db=db, ticket_id=ticket_id)

    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=f"No RCA analysis found for ticket_id='{ticket_id}'.",
        )

    return RCAAnalysisDetailResponse(
        ticket_id=analysis.ticket_id,
        site_id=analysis.site_id,
        site_name=analysis.site_name,
        region=analysis.region,
        priority=analysis.priority,
        description=analysis.description,
        predicted_family=analysis.predicted_family,
        confidence=analysis.confidence,
        top_hypotheses=[
            HypothesisItem(**item)
            for item in (analysis.top3_hypotheses_json or [])
        ],
        kpi_insights=analysis.kpi_insights_json or [],
        recommended_checks=analysis.recommended_checks_json or [],
        recommended_actions=analysis.recommended_actions_json or [],
        draft_report=analysis.draft_report,
        analysis_status=analysis.status,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
    )


@router.get("/reports/{ticket_id}", response_model=RCAReportResponse)
def get_report_endpoint(
    ticket_id: str,
    db: Session = Depends(get_db),
) -> RCAReportResponse:
    report = get_report_by_ticket_id(db=db, ticket_id=ticket_id)

    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"No RCA report found for ticket_id='{ticket_id}'.",
        )

    return RCAReportResponse(
        ticket_id=report.ticket_id,
        report_id=report.report_id,
        report_status=report.report_status,
        report_text=report.report_text,
        generated_at=report.generated_at,
    )


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

        enriched = build_enriched_rca_payload(
            predicted_family=result["predicted_family"],
            confidence=result["confidence"],
            top_hypotheses=result["top_hypotheses"],
            payload=payload_dict,
            kpi_insights=kpi_insights,
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

        return _build_analysis_response(
            saved=saved,
            result=result,
            kpi_insights=kpi_insights,
            recommended_checks=recommended_checks,
            recommended_actions=recommended_actions,
            draft_report=draft_report,
            enriched=enriched,
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


@router.post("/tickets/{ticket_id}/analyze-and-save", response_model=AnalyzeIncidentResponse)
def analyze_existing_ticket_and_save(
    ticket_id: str,
    top_k: int = 3,
    db: Session = Depends(get_db),
) -> AnalyzeIncidentResponse:
    service = get_service()

    if not service.is_trained or service.model is None:
        raise HTTPException(status_code=503, detail="Model artifacts are not loaded.")

    try:
        incident_df = load_training_dataframe()

        if "ticket_id" not in incident_df.columns:
            raise HTTPException(
                status_code=500,
                detail="RCA training dataframe does not contain ticket_id.",
            )

        matches = incident_df.loc[
            incident_df["ticket_id"].astype(str) == str(ticket_id)
        ]

        if matches.empty:
            raise HTTPException(
                status_code=404,
                detail=f"Ticket '{ticket_id}' not found in RCA dataset.",
            )

        row = matches.iloc[0].copy()

        target_column = getattr(service, "target_column", None)
        drop_columns = []

        if target_column:
            drop_columns.append(target_column)

        for possible_target in [
            "famille_de_problemes",
            "rca_family",
            "family",
            "label",
            "target",
        ]:
            if possible_target not in drop_columns:
                drop_columns.append(possible_target)

        payload_dict = row.drop(
            labels=drop_columns,
            errors="ignore",
        ).to_dict()

        payload_dict = _to_json_safe_payload(payload_dict)

        payload_dict["ticket_id"] = payload_dict.get("ticket_id") or ticket_id
        payload_dict["ticket_text"] = (
            payload_dict.get("ticket_text")
            or payload_dict.get("description")
            or f"RCA dataset ticket {ticket_id}"
        )
        payload_dict["site_name"] = (
            payload_dict.get("site_name")
            or payload_dict.get("nom_du_site")
            or payload_dict.get("site_id")
        )
        payload_dict["nom_du_site"] = (
            payload_dict.get("nom_du_site")
            or payload_dict.get("site_name")
            or payload_dict.get("site_id")
        )
        payload_dict["region"] = payload_dict.get("region") or str(
            payload_dict.get("site_id") or ""
        ).split("_")[0]

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
            ticket_id=payload_dict.get("ticket_id") or ticket_id,
            predicted_family=result["predicted_family"],
            confidence=result["confidence"],
            top_hypotheses=result["top_hypotheses"],
            kpi_insights=kpi_insights,
            recommended_checks=recommended_checks,
            recommended_actions=recommended_actions,
            payload=payload_dict,
        )

        enriched = build_enriched_rca_payload(
            predicted_family=result["predicted_family"],
            confidence=result["confidence"],
            top_hypotheses=result["top_hypotheses"],
            payload=payload_dict,
            kpi_insights=kpi_insights,
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

        return _build_analysis_response(
            saved=saved,
            result=result,
            kpi_insights=kpi_insights,
            recommended_checks=recommended_checks,
            recommended_actions=recommended_actions,
            draft_report=draft_report,
            enriched=enriched,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Dataset ticket analysis failed: {str(e)}",
        )


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
        raise HTTPException(
            status_code=404,
            detail=f"No runbook found for ticket_id='{ticket_id}'.",
        )

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