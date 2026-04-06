"""Data models for inter-module communication.

All modules exchange these Pydantic models as JSON via stdin/stdout.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# --- Enums ---


class DataClassification(str, Enum):
    public = "public"
    internal = "internal"
    confidential = "confidential"
    restricted = "restricted"


class HostingType(str, Enum):
    saas = "saas"
    iaas = "iaas"
    paas = "paas"
    on_premise = "on-premise"
    hybrid = "hybrid"


class EncryptionType(str, Enum):
    at_rest = "at-rest"
    in_transit = "in-transit"
    both = "both"
    none = "none"


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class Verdict(str, Enum):
    passed = "pass"
    fail = "fail"
    conditional = "conditional"
    insufficient_info = "insufficient_info"


class OverallVerdict(str, Enum):
    approved = "approved"
    rejected = "rejected"
    conditional = "conditional"


# --- Intake I/O ---


class MaterialItem(BaseModel):
    """A single piece of application material."""

    type: str = Field(description="Material type: 'text' or 'file'")
    content: str | None = Field(
        default=None, description="Text content (when type='text')"
    )
    path: str | None = Field(
        default=None, description="File path (when type='file')"
    )
    mime_type: str | None = Field(
        default=None,
        description="MIME type for file (auto-detected if omitted)",
    )


class IntakeAnswer(BaseModel):
    """An answer to a question raised during intake Phase 2."""

    field: str = Field(description="Target field name")
    question: str = Field(description="The question that was asked")
    response: str = Field(description="The applicant's response")


class IntakeInput(BaseModel):
    """Input to vr-intake module."""

    materials: list[MaterialItem] = Field(
        description="Application materials (text, images, documents)"
    )
    answers: list[IntakeAnswer] | None = Field(
        default=None,
        description="Answers to questions from previous pass (null on first pass)",
    )


class IntakeQuestion(BaseModel):
    """A question generated during intake validation."""

    field: str = Field(description="Target field in ApplicationRecord")
    question: str = Field(description="Question to ask the applicant")
    reason: str = Field(description="Why this information is needed")


class IntakeOutput(BaseModel):
    """Output from vr-intake module."""

    record: ApplicationRecord = Field(description="Structured application data")
    questions: list[IntakeQuestion] = Field(
        default_factory=list,
        description="Questions for the applicant (empty = record is complete)",
    )


# --- ApplicationRecord ---


class Applicant(BaseModel):
    name: str = ""
    department: str = ""
    contact: str = ""


class DataFlow(BaseModel):
    src: str = Field(description="Data source")
    dst: str = Field(description="Data destination")
    data_type: str = Field(description="Type of data")
    classification: DataClassification = DataClassification.internal


class Service(BaseModel):
    name: str
    vendor: str = ""
    hosting: HostingType = HostingType.saas
    auth_method: str = ""


class DataStore(BaseModel):
    type: str = Field(description="Storage type")
    encryption: EncryptionType = EncryptionType.none
    location: str = ""
    retention: str = ""


class ApplicationRecord(BaseModel):
    """Structured application data produced by intake."""

    application_id: str = ""
    submitted_at: datetime = Field(default_factory=datetime.now)
    applicant: Applicant = Field(default_factory=Applicant)
    system_overview: str = ""
    data_flows: list[DataFlow] = Field(default_factory=list)
    services: list[Service] = Field(default_factory=list)
    data_stores: list[DataStore] = Field(default_factory=list)
    confidence: dict[str, float] = Field(
        default_factory=dict,
        description="Confidence score (0.0-1.0) per field",
    )
    unresolved: list[IntakeAnswer] = Field(
        default_factory=list,
        description="Dialog log from Phase 2",
    )


# --- ExpertProfile ---


class RegulationRef(BaseModel):
    model_config = {"populate_by_name": True}

    section_id: str = Field(
        description="Regulation section ID (e.g. '1.2')",
        alias="id",
    )
    title: str = Field(description="Section title")


class ExpertProfile(BaseModel):
    """Expert model definition produced by persona compiler."""

    expert_id: str
    domain: str = Field(description="Expert domain (e.g. 'Authentication')")
    system_prompt: str
    regulation_text: str = Field(
        description="Full text of assigned regulation (loaded into context)"
    )
    required_fields: list[str] = Field(
        default_factory=list,
        description="ApplicationRecord fields needed for evaluation",
    )
    regulation_refs: list[RegulationRef] = Field(default_factory=list)
    version: str = ""


# --- ExpertVerdict ---


class Finding(BaseModel):
    """A single finding from an expert evaluation."""

    regulation_ref: str = Field(description="Regulation section ID")
    target_field: str = Field(
        description="ApplicationRecord field this finding relates to"
    )
    severity: Severity
    finding: str
    recommendation: str = ""


class ExpertVerdict(BaseModel):
    """Evaluation result from a single expert model."""

    expert_id: str
    verdict: Verdict
    findings: list[Finding] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


# --- FinalAssessment ---


class Conflict(BaseModel):
    """A conflict detected between two expert verdicts."""

    expert_a: str
    expert_b: str
    target_field: str
    description: str
    resolution: str


class EvidenceStep(BaseModel):
    """A single step in the audit trail."""

    step: int
    module: str
    input_hash: str
    output_hash: str
    timestamp: datetime = Field(default_factory=datetime.now)


class RiskSummary(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0


class FinalAssessment(BaseModel):
    """Final integrated assessment produced by brain unit."""

    assessment_id: str = ""
    application_id: str = ""
    assessed_at: datetime = Field(default_factory=datetime.now)
    overall_verdict: OverallVerdict
    conditions: list[str] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    risk_summary: RiskSummary = Field(default_factory=RiskSummary)
    findings: list[Finding] = Field(default_factory=list)
    evidence_chain: list[EvidenceStep] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)


# Forward reference update
IntakeOutput.model_rebuild()
