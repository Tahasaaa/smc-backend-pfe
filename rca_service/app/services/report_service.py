from __future__ import annotations

from typing import Any, Dict, List, Optional


FAMILY_PLAYBOOK = {
    "Transmission": {
        "checks": [
            "Check transmission alarms and backhaul link status.",
            "Verify transport latency, packet loss, and interface errors.",
            "Validate microwave or fiber availability for the impacted site.",
        ],
        "actions": [
            "Stabilize or reroute the affected transport path.",
            "Coordinate with transmission team for link recovery.",
            "Monitor service KPIs after transport restoration.",
        ],
        "conclusion": "Likely transport or backhaul degradation affecting service continuity.",
    },
    "Radio Access": {
        "checks": [
            "Inspect cell availability, radio alarms, and sector health.",
            "Review handover behavior, interference indicators, and access failures.",
            "Validate neighbor relations and radio configuration consistency.",
        ],
        "actions": [
            "Correct radio configuration or neighbor issues.",
            "Investigate sector hardware, feeder, or interference conditions.",
            "Re-test accessibility and mobility KPIs after intervention.",
        ],
        "conclusion": "Likely radio-layer degradation affecting access or mobility.",
    },
    "Performance": {
        "checks": [
            "Review throughput, congestion, and load distribution KPIs.",
            "Check whether the issue aligns with traffic pressure or localized overload.",
            "Verify whether user experience degradation matches KPI deterioration.",
        ],
        "actions": [
            "Apply performance optimization on impacted cells.",
            "Rebalance load or adjust parameters if congestion is confirmed.",
            "Track post-change KPI recovery over subsequent periods.",
        ],
        "conclusion": "Likely performance degradation driven by congestion or optimization gaps.",
    },
    "Préventif": {
        "checks": [
            "Review preventive indicators and early degradation signals.",
            "Verify if repeated weak KPI patterns are emerging on the site.",
            "Check whether the current issue suggests a developing fault.",
        ],
        "actions": [
            "Schedule preventive maintenance or site verification.",
            "Track the site closely for recurring abnormal behavior.",
            "Document early warning patterns for future reuse.",
        ],
        "conclusion": "Likely early-stage degradation suitable for preventive handling.",
    },
}


def _playbook_for_family(family: str) -> Dict[str, Any]:
    return FAMILY_PLAYBOOK.get(
        family,
        {
            "checks": [
                "Review available KPI evidence and impacted services.",
                "Validate whether the anomaly is persistent or transient.",
            ],
            "actions": [
                "Escalate for deeper RCA review.",
                "Collect additional evidence before final action.",
            ],
            "conclusion": "Cause remains uncertain and needs additional validation.",
        },
    )


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_low(payload: Dict[str, Any], key: str, threshold: float) -> bool:
    value = _safe_float(payload.get(key))
    return value is not None and value < threshold


def _is_high(payload: Dict[str, Any], key: str, threshold: float) -> bool:
    value = _safe_float(payload.get(key))
    return value is not None and value > threshold


def _has_repeated_pattern(payload: Dict[str, Any]) -> bool:
    matched = _safe_float(payload.get("matched_incident_count"))
    return matched is not None and matched >= 3


def _is_high_risk(payload: Dict[str, Any]) -> bool:
    potential = _safe_float(payload.get("incident_potential"))
    return potential is not None and potential >= 0.8


def _unique(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []

    for item in items:
        normalized = item.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    return result


def build_kpi_insights(payload: Dict[str, Any]) -> List[str]:
    insights: List[str] = []

    if _is_low(payload, "kpi_3g_cssr_ps", 95):
        insights.append(f"3G CSSR PS is weak at {payload.get('kpi_3g_cssr_ps')}.")
    if _is_low(payload, "kpi_3g_shosr", 95):
        insights.append(f"3G SHO success rate is degraded at {payload.get('kpi_3g_shosr')}.")
    if _is_low(payload, "kpi_3g_throughput", 4000):
        insights.append(f"3G throughput is low at {payload.get('kpi_3g_throughput')}.")
    if _is_high(payload, "kpi_3g_dropcall_cs", 2):
        insights.append(f"3G CS drop call rate is elevated at {payload.get('kpi_3g_dropcall_cs')}.")
    if _is_low(payload, "kpi_3g_cs_rab_setup_sr", 95):
        insights.append(f"3G CS RAB setup success rate is weak at {payload.get('kpi_3g_cs_rab_setup_sr')}.")
    if _is_low(payload, "kpi_3g_cs_interrat_ho_sr", 95):
        insights.append(f"3G CS inter-RAT HO success rate is weak at {payload.get('kpi_3g_cs_interrat_ho_sr')}.")

    if _is_high_risk(payload):
        insights.append(f"Incident potential is high at {payload.get('incident_potential')}.")
    if _has_repeated_pattern(payload):
        insights.append(f"Matched incident count suggests repeated pattern: {payload.get('matched_incident_count')}.")

    if payload.get("frequency_band"):
        insights.append(f"Reported frequency band context: {payload.get('frequency_band')}.")
    if payload.get("incident_status"):
        insights.append(f"Incident status context: {payload.get('incident_status')}.")

    if not insights:
        insights.append("Limited KPI context provided; prediction is mainly driven by available text and sparse metadata.")

    return _unique(insights)


def build_recommended_checks(
    predicted_family: str,
    payload: Dict[str, Any],
    kpi_insights: List[str],
) -> List[str]:
    checks = list(_playbook_for_family(predicted_family)["checks"])

    if payload.get("site_id"):
        checks.insert(0, f"Validate impacted site context for site_id={payload['site_id']}.")
    if payload.get("ticket_text"):
        checks.append("Cross-check field observations against the incident description.")
    if _has_repeated_pattern(payload):
        checks.append("Compare with previous similar incidents for the same site or pattern.")
    if _is_high_risk(payload):
        checks.append("Prioritize validation because the incident potential is high.")

    if predicted_family == "Transmission":
        if _is_low(payload, "kpi_3g_throughput", 4000):
            checks.append("Correlate throughput degradation with backhaul saturation or transport instability.")
        if _is_high(payload, "kpi_3g_dropcall_cs", 2):
            checks.append("Check whether call drops align with transport interruptions or packet loss.")
        if _is_low(payload, "kpi_3g_cs_rab_setup_sr", 95):
            checks.append("Verify whether RAB setup weakness is linked to transport path instability.")

    elif predicted_family == "Radio Access":
        if _is_low(payload, "kpi_3g_shosr", 95) or _is_low(payload, "kpi_3g_cs_interrat_ho_sr", 95):
            checks.append("Review handover configuration, neighbors, and mobility consistency.")
        if _is_high(payload, "kpi_3g_dropcall_cs", 2):
            checks.append("Inspect radio drops against sector alarms, feeders, and RF degradation.")
        if _is_low(payload, "kpi_3g_cssr_ps", 95):
            checks.append("Check accessibility weakness against radio access failures and admission issues.")

    elif predicted_family == "Performance":
        if _is_low(payload, "kpi_3g_throughput", 4000):
            checks.append("Check whether low throughput is driven by congestion, load imbalance, or weak scheduling.")
        if _is_low(payload, "kpi_3g_cssr_ps", 95):
            checks.append("Review whether degraded setup success is reducing service performance perception.")
        if _is_high_risk(payload):
            checks.append("Validate whether user experience impact is already significant enough for rapid optimization.")

    elif predicted_family == "Préventif":
        if _has_repeated_pattern(payload):
            checks.append("Confirm whether this weak pattern has appeared repeatedly and should be tracked proactively.")
        if _is_low(payload, "kpi_3g_shosr", 95) or _is_low(payload, "kpi_3g_cssr_ps", 95):
            checks.append("Check if weak KPI drift is an early sign of configuration or hardware degradation.")
        if _is_low(payload, "kpi_3g_throughput", 4000):
            checks.append("Review whether throughput degradation is recurring before becoming a major incident.")

    return _unique(checks)


def build_recommended_actions(
    predicted_family: str,
    payload: Dict[str, Any],
    kpi_insights: List[str],
) -> List[str]:
    actions = list(_playbook_for_family(predicted_family)["actions"])

    if payload.get("priorite") or payload.get("priorite_texte"):
        actions.append("Apply escalation handling consistent with incident priority.")
    if _has_repeated_pattern(payload):
        actions.append("Reference similar historical cases before final closure.")
    if _is_high_risk(payload):
        actions.append("Escalate validation and remediation timing because the site risk is high.")

    if predicted_family == "Transmission":
        if _is_low(payload, "kpi_3g_throughput", 4000):
            actions.append("Coordinate transport troubleshooting before applying radio-side parameter changes.")
        if _is_high(payload, "kpi_3g_dropcall_cs", 2):
            actions.append("Monitor voice stability immediately after transmission recovery.")

    elif predicted_family == "Radio Access":
        if _is_low(payload, "kpi_3g_shosr", 95) or _is_low(payload, "kpi_3g_cs_interrat_ho_sr", 95):
            actions.append("Tune mobility and neighbor configuration if handover weakness is confirmed.")
        if _is_high(payload, "kpi_3g_dropcall_cs", 2):
            actions.append("Dispatch radio investigation for sector-level RF or hardware verification.")
        if _is_low(payload, "kpi_3g_cssr_ps", 95):
            actions.append("Validate accessibility recovery after radio-side corrective action.")

    elif predicted_family == "Performance":
        if _is_low(payload, "kpi_3g_throughput", 4000):
            actions.append("Apply performance tuning and monitor throughput recovery on the impacted site.")
        if _has_repeated_pattern(payload):
            actions.append("Create optimization follow-up because the pattern appears recurrent.")

    elif predicted_family == "Préventif":
        actions.append("Keep the case documented as a preventive pattern for future reuse.")
        if _has_repeated_pattern(payload):
            actions.append("Schedule targeted preventive maintenance for the recurring degradation pattern.")

    return _unique(actions)


def build_draft_report(
    ticket_id: str,
    predicted_family: str,
    confidence: float,
    top_hypotheses: List[Dict[str, Any]],
    kpi_insights: List[str],
    recommended_checks: List[str],
    recommended_actions: List[str],
    payload: Dict[str, Any],
) -> str:
    site_name = payload.get("site_name") or payload.get("nom_du_site") or "Unknown site"
    region = payload.get("region") or "Unknown region"
    description = payload.get("ticket_text") or "No incident description provided."

    hypotheses_text = "\n".join(
        f"- {item['family']}: {item['probability']:.4f}"
        for item in top_hypotheses
    )
    insights_text = "\n".join(f"- {x}" for x in kpi_insights)
    checks_text = "\n".join(f"- {x}" for x in recommended_checks)
    actions_text = "\n".join(f"- {x}" for x in recommended_actions)

    confidence_note = (
        "Low-confidence result: engineer review of top hypotheses is strongly recommended."
        if confidence < 0.60
        else "Confidence is reasonably usable for guided RCA review."
    )

    return f"""RCA Draft Report
Ticket ID: {ticket_id}
Site: {site_name}
Region: {region}

Incident Summary:
{description}

Predicted RCA Family:
- {predicted_family}
- Confidence: {confidence:.4f}
- Interpretation: {confidence_note}

Top Hypotheses:
{hypotheses_text}

KPI Insights:
{insights_text}

Recommended Checks:
{checks_text}

Recommended Actions:
{actions_text}
""".strip()


def build_final_report(analysis, approval) -> str:
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

    conclusion = _playbook_for_family(chosen_family)["conclusion"]

    if confidence >= 0.90:
        confidence_label = "Very high confidence"
        engineer_review_note = "The model output is strong and suitable for guided RCA validation."
    elif confidence >= 0.75:
        confidence_label = "High confidence"
        engineer_review_note = "The model output is usable, with engineer confirmation recommended."
    elif confidence >= 0.60:
        confidence_label = "Medium confidence"
        engineer_review_note = "The model output should be reviewed carefully before operational closure."
    else:
        confidence_label = "Low confidence"
        engineer_review_note = "The model output should be treated as exploratory and requires strong engineer validation."

    if chosen_family == "Transmission":
        root_cause_statement = (
            "The approved RCA indicates a probable transmission or backhaul degradation. "
            "The issue may affect throughput stability, packet delivery, latency, and service continuity."
        )
        risk_impact = (
            "If not fixed, the incident may evolve into wider service instability, repeated degradation, "
            "throughput collapse, packet loss, and possible cascading impact on dependent sites."
        )
        estimated_fix_window = "0-4 hours for critical validation, then continuous monitoring after recovery."

    elif chosen_family == "Radio Access":
        root_cause_statement = (
            "The approved RCA indicates a probable radio access degradation. "
            "The issue may affect accessibility, handover behavior, dropped calls, or sector-level quality."
        )
        risk_impact = (
            "If not fixed, users may experience access failures, mobility failures, call drops, "
            "and persistent radio quality degradation."
        )
        estimated_fix_window = "0-8 hours depending on site accessibility and radio investigation results."

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

    elif chosen_family == "Préventif":
        root_cause_statement = (
            "The approved RCA indicates an early degradation pattern requiring preventive handling. "
            "The objective is to avoid escalation into a major incident."
        )
        risk_impact = (
            "If ignored, the pattern may become recurrent and later evolve into a confirmed service-impacting incident."
        )
        estimated_fix_window = "24-48 hours for preventive verification and follow-up monitoring."

    else:
        root_cause_statement = (
            "The approved RCA indicates a probable operational degradation that requires further validation."
        )
        risk_impact = (
            "If not fixed, the incident may continue affecting network stability and user experience."
        )
        estimated_fix_window = "To be estimated by the responsible operations team."

    chart_summary = """Chart Summary for Frontend Visualization:
- Hypothesis probability chart: use the top hypotheses and their confidence percentages.
- KPI evidence chart: use KPI insights as supporting degraded indicators.
- Risk timeline chart: show current risk, estimated escalation window, and expected impact if not fixed.
"""

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
{chart_summary}

10. Final Conclusion
{conclusion}
""".strip()


def build_runbook_fields(analysis, approval, report_text: str) -> Dict[str, Any]:
    family = approval.approved_family
    conclusion = _playbook_for_family(family)["conclusion"]

    return {
        "incident_summary": analysis.description or analysis.draft_report,
        "final_conclusion": approval.engineer_notes or conclusion,
        "checks_json": approval.approved_checks_json or [],
        "actions_json": approval.approved_actions_json or [],
    }