"""Shared API contracts with agreed Reading schema and continual-learning telemetry types."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


SourceType = Literal["synthetic", "measured", "operator-observed"]


class Reading(BaseModel):
    ts: str = Field(min_length=1)
    sensor: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    value: float
    unit: str = ""
    origin: str = "bot-01"


class Incident(BaseModel):
    id: str = Field(min_length=1)
    robot_type: str = Field(min_length=1)
    time_window: str = Field(min_length=1)
    commanded_action: str = Field(min_length=1)
    readings: list[Reading | dict[str, Any]]
    fault_codes: list[str]
    technician_note: str
    source_type: SourceType


class Diagnosis(BaseModel):
    cause_label: str = Field(min_length=1)
    supporting_evidence: list[str]
    alternative: str = Field(min_length=1)
    next_check: str = Field(min_length=1)
    uncertainty: Literal["low", "medium", "high"]
    recommended_command: dict[str, Any] | None = None


class DiagnoseRequest(BaseModel):
    incident_id: str = Field(min_length=1)


class DiagnosisRecord(BaseModel):
    id: str
    incident_id: str
    diagnosis: Diagnosis
    created_at: datetime
    request_reference: str | None = None
    model_id: str | None = None


class ConfirmRequest(BaseModel):
    diagnosis_id: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    actual_cause: str = Field(min_length=1)
    fix_performed: str = Field(min_length=1)
    verifier: str = Field(min_length=1)
    timestamp: datetime


class ConfirmationRecord(ConfirmRequest):
    id: str


class EvaluationCaseResult(BaseModel):
    incident_id: str
    expected_cause_label: str
    predicted_cause_label: str
    matched: bool
    uncertainty: Literal["low", "medium", "high"]


class EvaluationSummary(BaseModel):
    id: str
    total_cases: int
    matched_cases: int
    accuracy_pct: float
    results: list[EvaluationCaseResult]
    created_at: datetime


class Metrics(BaseModel):
    incident_count: int
    diagnosis_count: int
    confirmation_count: int
    evaluation_count: int = 0
    latest_accuracy_pct: float | None = None
    provider_status: Literal["not_configured", "ready"] = "ready"
    task_status: Literal["unavailable", "ready"] = "ready"
    adapter_status: Literal["unavailable", "ready", "learning"] = "ready"
    simulator_online: bool = False
