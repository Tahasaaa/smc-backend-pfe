from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import RCAAnalysis, RCAApproval, RCAReport, RunbookEntry
from app.services.report_service import build_runbook_fields


def ensure_ticket_id(ticket_id: Optional[str]) -> str:
    if ticket_id and str(ticket_id).strip():
        return str(ticket_id).strip()
    return f"AUTO-{uuid4().hex[:12].upper()}"


def get_analysis_by_ticket_id(db: Session, ticket_id: str) -> Optional[RCAAnalysis]:
    return db.query(RCAAnalysis).filter(RCAAnalysis.ticket_id == ticket_id).first()


def get_approval_by_ticket_id(db: Session, ticket_id: str) -> Optional[RCAApproval]:
    return db.query(RCAApproval).filter(RCAApproval.ticket_id == ticket_id).first()


def get_report_by_ticket_id(db: Session, ticket_id: str) -> Optional[RCAReport]:
    return db.query(RCAReport).filter(RCAReport.ticket_id == ticket_id).first()


def get_runbook_by_ticket_id(db: Session, ticket_id: str) -> Optional[RunbookEntry]:
    return db.query(RunbookEntry).filter(RunbookEntry.ticket_id == ticket_id).first()


def upsert_analysis(
    db: Session,
    payload: Dict[str, Any],
    prediction: Dict[str, Any],
    kpi_insights: List[str],
    recommended_checks: List[str],
    recommended_actions: List[str],
    draft_report: str,
) -> RCAAnalysis:
    ticket_id = ensure_ticket_id(payload.get("ticket_id"))
    analysis = get_analysis_by_ticket_id(db, ticket_id)

    if analysis is None:
        analysis = RCAAnalysis(ticket_id=ticket_id)
        db.add(analysis)

    analysis.site_id = payload.get("site_id")
    analysis.site_name = payload.get("site_name") or payload.get("nom_du_site")
    analysis.region = payload.get("region")
    analysis.priority = payload.get("priorite_texte") or payload.get("priorite")
    analysis.description = payload.get("ticket_text")

    analysis.predicted_family = prediction["predicted_family"]
    analysis.confidence = float(prediction["confidence"])

    analysis.top3_hypotheses_json = prediction["top_hypotheses"]
    analysis.kpi_insights_json = kpi_insights
    analysis.recommended_checks_json = recommended_checks
    analysis.recommended_actions_json = recommended_actions

    analysis.draft_report = draft_report
    analysis.status = "analysis_ready"

    db.commit()
    db.refresh(analysis)
    return analysis


def upsert_approval(
    db: Session,
    ticket_id: str,
    approved_by: str,
    approval_status: str,
    approved_family: Optional[str] = None,
    approved_checks: Optional[List[str]] = None,
    approved_actions: Optional[List[str]] = None,
    engineer_notes: Optional[str] = None,
) -> RCAApproval:
    analysis = get_analysis_by_ticket_id(db, ticket_id)
    if analysis is None:
        raise ValueError(f"No RCA analysis found for ticket_id='{ticket_id}'.")

    approval = get_approval_by_ticket_id(db, ticket_id)
    if approval is None:
        approval = RCAApproval(ticket_id=ticket_id)
        db.add(approval)

    approval.approved_family = approved_family or analysis.predicted_family
    approval.approved_checks_json = approved_checks or (
        analysis.recommended_checks_json or []
    )
    approval.approved_actions_json = approved_actions or (
        analysis.recommended_actions_json or []
    )
    approval.engineer_notes = engineer_notes
    approval.approved_by = approved_by
    approval.approval_status = approval_status

    analysis.status = "approved" if approval_status == "approved" else "rejected"

    db.commit()
    db.refresh(approval)
    return approval


def build_final_report_v2(analysis, approval) -> str:
    top_hypotheses = analysis.top3_hypotheses_json or []

    hypotheses_text = "\n".join(
        f"- {item.get('family')}: {float(item.get('probability', 0)) * 100:.2f}%"
        for item in top_hypotheses
    ) or "- None"

    checks = approval.approved_checks_json or []
    actions = approval.approved_actions_json or []
    insights = analysis.kpi_insights_json or []

    checks_text = (
        "\n".join(f"{idx + 1}. {x}" for idx, x in enumerate(checks))
        if checks
        else "1. None"
    )
    actions_text = (
        "\n".join(f"{idx + 1}. {x}" for idx, x in enumerate(actions))
        if actions
        else "1. None"
    )
    insights_text = "\n".join(f"- {x}" for x in insights) if insights else "- None"

    chosen_family = approval.approved_family
    model_family = analysis.predicted_family
    confidence = float(analysis.confidence or 0.0)
    confidence_percent = confidence * 100.0

    if confidence >= 0.90:
        confidence_label = "Very high confidence"
        engineer_review_note = (
            "The model output is strong and suitable for guided RCA validation."
        )
    elif confidence >= 0.75:
        confidence_label = "High confidence"
        engineer_review_note = (
            "The model output is usable, with engineer confirmation recommended."
        )
    elif confidence >= 0.60:
        confidence_label = "Medium confidence"
        engineer_review_note = (
            "The model output should be reviewed carefully before operational closure."
        )
    else:
        confidence_label = "Low confidence"
        engineer_review_note = (
            "The model output should be treated as exploratory and requires strong engineer validation."
        )

    if chosen_family == "Transmission":
        root_cause_statement = (
            "The approved RCA indicates a probable transmission or backhaul degradation. "
            "The issue may affect throughput stability, packet delivery, latency, and service continuity."
        )
        risk_impact = (
            "If not fixed, the incident may evolve into wider service instability, repeated degradation, "
            "throughput collapse, packet loss, and possible cascading impact on dependent sites."
        )
        estimated_fix_window = (
            "0-4 hours for critical validation, then continuous monitoring after recovery."
        )
        final_conclusion = (
            "Likely transport or backhaul degradation affecting service continuity."
        )

    elif chosen_family == "Radio Access":
        root_cause_statement = (
            "The approved RCA indicates a probable radio access degradation. "
            "The issue may affect accessibility, handover behavior, dropped calls, or sector-level quality."
        )
        risk_impact = (
            "If not fixed, users may experience access failures, mobility failures, call drops, "
            "and persistent radio quality degradation."
        )
        estimated_fix_window = (
            "0-8 hours depending on site accessibility and radio investigation results."
        )
        final_conclusion = "Likely radio-layer degradation affecting access or mobility."

    elif chosen_family == "Performance":
        root_cause_statement = (
            "The approved RCA indicates a probable performance degradation. "
            "The issue may be linked to congestion, traffic pressure, load imbalance, or optimization gaps."
        )
        risk_impact = (
            "If not fixed, the site may continue producing poor user experience, low throughput, "
            "high complaint volume, and repeated performance tickets."
        )
        estimated_fix_window = "4-24 hours depending on optimization or capacity actions."
        final_conclusion = (
            "Likely performance degradation driven by congestion or optimization gaps."
        )

    elif chosen_family == "Préventif":
        root_cause_statement = (
            "The approved RCA indicates an early degradation pattern requiring preventive handling. "
            "The objective is to avoid escalation into a major incident."
        )
        risk_impact = (
            "If ignored, the pattern may become recurrent and later evolve into a confirmed "
            "service-impacting incident."
        )
        estimated_fix_window = (
            "24-48 hours for preventive verification and follow-up monitoring."
        )
        final_conclusion = "Likely early-stage degradation suitable for preventive handling."

    else:
        root_cause_statement = (
            "The approved RCA indicates a probable operational degradation that requires further validation."
        )
        risk_impact = (
            "If not fixed, the incident may continue affecting network stability and user experience."
        )
        estimated_fix_window = "To be estimated by the responsible operations team."
        final_conclusion = "Cause remains uncertain and needs additional validation."

    return f"""Final RCA Report
Ticket ID: {analysis.ticket_id}
Site ID: {analysis.site_id or "N/A"}
Site Name: {analysis.site_name or "N/A"}
Region: {analysis.region or "N/A"}
Priority: {analysis.priority or "N/A"}

1. Incident Description
{analysis.description or "N/A"}

2. Approved Root Cause
Chosen hypothesis: {chosen_family}
Model predicted family: {model_family}
Model confidence: {confidence_percent:.2f}% ({confidence_label})

Root cause statement:
{root_cause_statement}

3. Top Model Hypotheses
{hypotheses_text}

4. KPI Evidence and Supporting Signals
{insights_text}

5. Engineer Validation
Approval status: {approval.approval_status}
Approved by: {approval.approved_by}

Engineer notes:
{approval.engineer_notes or "No engineer notes provided."}

Review note:
{engineer_review_note}

6. Recommended Checks / Diagnostic Steps
{checks_text}

7. Recommended Actions / Steps to Follow
{actions_text}

8. Risk If Not Fixed
Estimated operational impact:
{risk_impact}

Estimated intervention window:
{estimated_fix_window}

9. Chart Data Guidance
- Hypothesis probability chart: use top hypotheses and confidence percentages.
- KPI evidence chart: use KPI insights as degraded supporting indicators.
- Risk timeline chart: show current risk, escalation window, and expected operational impact if not fixed.

10. Final Conclusion
{final_conclusion}
""".strip()


def create_or_update_report(db: Session, ticket_id: str) -> RCAReport:
    analysis = get_analysis_by_ticket_id(db, ticket_id)
    if analysis is None:
        raise ValueError(f"No RCA analysis found for ticket_id='{ticket_id}'.")

    approval = get_approval_by_ticket_id(db, ticket_id)
    if approval is None:
        raise ValueError(f"No RCA approval found for ticket_id='{ticket_id}'.")

    if approval.approval_status != "approved":
        raise ValueError(
            f"Ticket '{ticket_id}' is not approved. Cannot generate final report."
        )

    report_text = build_final_report_v2(analysis, approval)

    report = get_report_by_ticket_id(db, ticket_id)
    if report is None:
        report = RCAReport(
            ticket_id=ticket_id,
            report_id=f"RPT-{ticket_id}",
        )
        db.add(report)

    report.report_text = report_text
    report.report_status = "generated"
    report.generated_at = datetime.now(timezone.utc)

    analysis.status = "report_generated"

    db.commit()
    db.refresh(report)
    return report


def publish_runbook(
    db: Session,
    ticket_id: str,
    created_by: Optional[str] = None,
    tags: Optional[List[str]] = None,
    is_reusable: str = "yes",
) -> RunbookEntry:
    analysis = get_analysis_by_ticket_id(db, ticket_id)
    if analysis is None:
        raise ValueError(f"No RCA analysis found for ticket_id='{ticket_id}'.")

    approval = get_approval_by_ticket_id(db, ticket_id)
    if approval is None:
        raise ValueError(f"No RCA approval found for ticket_id='{ticket_id}'.")

    if approval.approval_status != "approved":
        raise ValueError(
            f"Ticket '{ticket_id}' is not approved. Cannot publish runbook."
        )

    report = get_report_by_ticket_id(db, ticket_id)
    if report is None:
        raise ValueError(
            f"No RCA report found for ticket_id='{ticket_id}'. Generate the report first."
        )

    runbook = get_runbook_by_ticket_id(db, ticket_id)
    if runbook is None:
        runbook = RunbookEntry(ticket_id=ticket_id)
        db.add(runbook)

    derived = build_runbook_fields(analysis, approval, report.report_text)

    runbook.site_id = analysis.site_id
    runbook.site_name = analysis.site_name
    runbook.region = analysis.region
    runbook.approved_family = approval.approved_family
    runbook.incident_summary = derived["incident_summary"]
    runbook.final_conclusion = derived["final_conclusion"]
    runbook.checks_json = derived["checks_json"]
    runbook.actions_json = derived["actions_json"]
    runbook.engineer_notes = approval.engineer_notes
    runbook.report_id = report.report_id
    runbook.tags_json = tags or []
    runbook.is_reusable = is_reusable
    runbook.created_by = created_by or approval.approved_by

    analysis.status = "runbook_published"

    db.commit()
    db.refresh(runbook)
    return runbook


def search_runbooks(
    db: Session,
    q: Optional[str] = None,
    approved_family: Optional[str] = None,
    limit: int = 20,
) -> List[RunbookEntry]:
    limit = max(1, min(limit, 100))
    query = db.query(RunbookEntry)

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

    return query.order_by(RunbookEntry.created_at.desc()).limit(limit).all()