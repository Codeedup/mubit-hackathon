"""Shared API contracts. Owners A and B still need to agree on reading fields."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


SourceType = Literal["synthetic", "measured", "operator-observed"]


class Incident(BaseModel):
    id: str = Field(min_length=1)
    robot_type: str = Field(min_length=1)
    time_window: str = Field(min_length=1)
    commanded_action: str = Field(min_length=1)
    # TODO(owners A+B): replace this placeholder after agreeing the reading schema.
    readings: list[dict[str, Any]]
    fault_codes: list[str]
    technician_note: str
    source_type: SourceType


class Diagnosis(BaseModel):
    cause_label: str = Field(min_length=1)
    supporting_evidence: list[str]
    alternative: str = Field(min_length=1)
    next_check: str = Field(min_length=1)
    uncertainty: Literal["low", "medium", "high"]


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


class Metrics(BaseModel):
    incident_count: int
    diagnosis_count: int
    confirmation_count: int
    provider_status: Literal["not_configured"] = "not_configured"
    task_status: Literal["unavailable"] = "unavailable"
    adapter_status: Literal["unavailable"] = "unavailable"

