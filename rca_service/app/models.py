from sqlalchemy import Column, DateTime, Float, Integer, String, Text, JSON
from sqlalchemy.sql import func

from app.db import Base


class RCAAnalysis(Base):
    __tablename__ = "rca_analyses"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(String, unique=True, index=True, nullable=False)

    site_id = Column(String, nullable=True)
    site_name = Column(String, nullable=True)
    region = Column(String, nullable=True)
    priority = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    predicted_family = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)

    top3_hypotheses_json = Column(JSON, nullable=False)
    kpi_insights_json = Column(JSON, nullable=False)
    recommended_checks_json = Column(JSON, nullable=False)
    recommended_actions_json = Column(JSON, nullable=False)

    draft_report = Column(Text, nullable=False)
    status = Column(String, default="analysis_ready", nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class RCAApproval(Base):
    __tablename__ = "rca_approvals"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(String, index=True, nullable=False)

    approved_family = Column(String, nullable=False)
    approved_checks_json = Column(JSON, nullable=False, default=list)
    approved_actions_json = Column(JSON, nullable=False, default=list)
    engineer_notes = Column(Text, nullable=True)

    approved_by = Column(String, nullable=False)
    approval_status = Column(String, default="approved", nullable=False)
    approved_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class RCAReport(Base):
    __tablename__ = "rca_reports"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(String, unique=True, index=True, nullable=False)

    report_id = Column(String, unique=True, nullable=False)
    report_text = Column(Text, nullable=False)
    report_status = Column(String, default="generated", nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class RunbookEntry(Base):
    __tablename__ = "runbook_entries"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(String, unique=True, index=True, nullable=False)

    site_id = Column(String, nullable=True)
    site_name = Column(String, nullable=True)
    region = Column(String, nullable=True)

    approved_family = Column(String, nullable=False)
    incident_summary = Column(Text, nullable=True)
    final_conclusion = Column(Text, nullable=True)

    checks_json = Column(JSON, nullable=False, default=list)
    actions_json = Column(JSON, nullable=False, default=list)
    engineer_notes = Column(Text, nullable=True)

    report_id = Column(String, nullable=True)
    tags_json = Column(JSON, nullable=False, default=list)
    is_reusable = Column(String, default="yes", nullable=False)
    created_by = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)