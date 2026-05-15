from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class HypothesisItem(BaseModel):
    family: str
    probability: float


class AnalyzeIncidentRequest(BaseModel):
    ticket_id: Optional[str] = None
    ticket_text: str
    site_id: Optional[str] = None
    origine: Optional[str] = None
    etat: Optional[str] = None
    type_ticket: Optional[str] = None
    priorite: Optional[str] = None
    priorite_texte: Optional[str] = None
    nom_du_site: Optional[str] = None
    site_name: Optional[str] = None
    region: Optional[str] = None
    incident_status: Optional[str] = None
    frequency_band: Optional[str] = None

    date_debut: Optional[str] = None
    date_d_acquittement: Optional[str] = None
    date_de_reparation: Optional[str] = None
    date_de_cloture: Optional[str] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    kpi_3g_cssr_ps: Optional[float] = None
    kpi_3g_shosr: Optional[float] = None
    kpi_3g_throughput: Optional[float] = None
    kpi_3g_dropcall_cs: Optional[float] = None
    kpi_3g_cs_rab_setup_sr: Optional[float] = None
    kpi_3g_cs_interrat_ho_sr: Optional[float] = None

    incident_potential: Optional[float] = None
    matched_incident_count: Optional[float] = None
    incident_mapping_confidence: Optional[float] = None
    worst_priority_code: Optional[float] = None
    engineering_record_count: Optional[float] = None

    top_k: int = Field(default=3, ge=1, le=5)


class AnalyzeIncidentResponse(BaseModel):
    predicted_family: str
    confidence: float
    top_hypotheses: List[HypothesisItem]
    ticket_id: str
    analysis_status: str

    kpi_insights: List[str] = Field(default_factory=list)
    recommended_checks: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    draft_report: Optional[str] = None

    root_cause_summary: Dict[str, Any] = Field(default_factory=dict)
    risk_if_not_fixed: Dict[str, Any] = Field(default_factory=dict)
    charts: Dict[str, Any] = Field(default_factory=dict)
    explainability_status: Dict[str, Any] = Field(default_factory=dict)


class RCAApprovalRequest(BaseModel):
    ticket_id: str
    approved_by: str
    approved_family: Optional[str] = None
    approved_checks: List[str] = Field(default_factory=list)
    approved_actions: List[str] = Field(default_factory=list)
    engineer_notes: Optional[str] = None
    approval_status: Literal["approved", "rejected"] = "approved"


class RCAApprovalResponse(BaseModel):
    ticket_id: str
    approval_status: str
    approved_family: str
    approved_checks: List[str]
    approved_actions: List[str]
    engineer_notes: Optional[str] = None
    approved_by: str
    approved_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RCAReportGenerateRequest(BaseModel):
    ticket_id: str


class RCAReportResponse(BaseModel):
    ticket_id: str
    report_id: str
    report_status: str
    report_text: str
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunbookPublishRequest(BaseModel):
    ticket_id: str
    created_by: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    is_reusable: str = "yes"


class RunbookEntryResponse(BaseModel):
    ticket_id: str
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    region: Optional[str] = None
    approved_family: str
    incident_summary: Optional[str] = None
    final_conclusion: Optional[str] = None
    checks: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    engineer_notes: Optional[str] = None
    report_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    is_reusable: str
    created_by: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunbookSearchResponse(BaseModel):
    total: int
    items: List[RunbookEntryResponse]

class RCAAnalysisDetailResponse(BaseModel):
    ticket_id: str
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    region: Optional[str] = None
    priority: Optional[str] = None
    description: Optional[str] = None

    predicted_family: str
    confidence: float
    top_hypotheses: List[HypothesisItem] = Field(default_factory=list)

    kpi_insights: List[str] = Field(default_factory=list)
    recommended_checks: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    draft_report: Optional[str] = None

    analysis_status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)