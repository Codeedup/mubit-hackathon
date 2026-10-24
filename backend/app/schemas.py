"""Versioned contracts shared by incident files and API responses."""

from datetime import datetime
from math import isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SourceType = Literal["synthetic", "measured", "operator-observed"]
KnownCause = Literal[
    "wheel obstruction", "motor power/driver path", "encoder/reporting fault"
]
CauseLabel = Literal[
    "wheel obstruction", "motor power/driver path", "encoder/reporting fault", "unknown"
]
ProviderKind = Literal["local_fixture", "mubit"]
VerificationKind = Literal["inspection", "synthetic_simulation"]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Reading(StrictModel):
    sensor: str = Field(min_length=1)
    value: float | str | bool
    unit: str = Field(min_length=1)
    origin: SourceType
    time: datetime

    @field_validator("time")
    @classmethod
    def time_has_timezone(cls, value: datetime) -> datetime:
        return _aware(value)

    @field_validator("value")
    @classmethod
    def value_is_present(cls, value: float | str | bool) -> float | str | bool:
        if isinstance(value, str) and not value.strip():
            raise ValueError("reading value cannot be blank")
        if isinstance(value, float) and not isfinite(value):
            raise ValueError("reading value must be finite")
        return value


class Incident(StrictModel):
    schema_version: Literal["1.0"]
    id: str = Field(min_length=1)
    robot_type: str = Field(min_length=1)
    time_window: str = Field(min_length=1)
    commanded_action: str = Field(min_length=1)
    readings: list[Reading] = Field(min_length=1)
    fault_codes: list[str]
    technician_note: str
    source_type: SourceType

    @model_validator(mode="after")
    def synthetic_readings_are_labelled(self) -> "Incident":
        if self.source_type == "synthetic" and any(
            reading.origin != "synthetic" for reading in self.readings
        ):
            raise ValueError("synthetic incident readings must have synthetic origin")
        if self.source_type != "synthetic" and any(
            reading.origin == "synthetic" for reading in self.readings
        ):
            raise ValueError("physical incident readings cannot have synthetic origin")
        return self

    @field_validator("fault_codes")
    @classmethod
    def fault_codes_are_nonblank(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("fault codes cannot be blank")
        return values


class EvidenceReference(StrictModel):
    field: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class Diagnosis(StrictModel):
    cause_label: CauseLabel
    supporting_evidence: list[EvidenceReference] = Field(min_length=1)
    alternative: str = Field(min_length=1)
    next_check: str = Field(min_length=1)
    uncertainty: Literal["low", "medium", "high"]

    @model_validator(mode="after")
    def unknown_is_uncertain(self) -> "Diagnosis":
        if self.cause_label == "unknown" and self.uncertainty != "high":
            raise ValueError("unknown cause must have high uncertainty")
        return self


class DiagnoseRequest(StrictModel):
    incident_id: str = Field(min_length=1)


class DiagnosisRecord(StrictModel):
    id: str
    incident_id: str
    incident: Incident
    diagnosis: Diagnosis
    created_at: datetime
    request_reference: str
    model_id: str
    provider_kind: ProviderKind
    raw_response: str


class ConfirmRequest(StrictModel):
    diagnosis_id: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    actual_cause: str = Field(min_length=1)
    fix_performed: str = Field(min_length=1)
    inspection_note: str = Field(min_length=1)
    verifier: str = Field(min_length=1)
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def timestamp_has_timezone(cls, value: datetime) -> datetime:
        return _aware(value)


class ConfirmationRecord(ConfirmRequest):
    id: str
    verification_kind: VerificationKind


class RepairRecord(ConfirmationRecord):
    predicted_cause: CauseLabel
    diagnosis_created_at: datetime
    provider_kind: ProviderKind
    model_id: str
    matched: bool


class ConfirmedEvaluationCase(StrictModel):
    diagnosis_id: str
    incident_id: str
    predicted_cause: CauseLabel
    actual_cause: str
    matched: bool


class ConfirmedEvaluation(StrictModel):
    provider_kind: ProviderKind
    model_id: str
    total: int
    confirmed_diagnosis_count: int
    matched: int
    accuracy: float | None
    cases: list[ConfirmedEvaluationCase]


class ConfirmedEvaluationReport(StrictModel):
    source: Literal["technician_confirmed"] = "technician_confirmed"
    groups: list[ConfirmedEvaluation]


class Metrics(StrictModel):
    incident_count: int
    diagnosis_count: int
    confirmation_count: int
    provider_status: Literal["not_configured", "local_fixture"]
    task_status: Literal["unavailable"] = "unavailable"
    adapter_status: Literal["unavailable"] = "unavailable"
    simulator_online: bool = False
