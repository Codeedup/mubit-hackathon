"""Parse provider output and keep only diagnoses grounded in the supplied case."""

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from .provider import DiagnosisProvider, ProviderFailure
from .schemas import Diagnosis, DiagnosisRecord, Incident


_EVIDENCE_PATH = re.compile(
    r"^(?:robot_type|time_window|commanded_action|technician_note|source_type|"
    r"fault_codes\[(\d+)\]|readings\[(\d+)\]\.(sensor|value|unit|origin|time))$"
)


def _evidence_exists(incident: Incident, field: str) -> bool:
    match = _EVIDENCE_PATH.fullmatch(field)
    if match is None:
        return False
    fault_index, reading_index, _part = match.groups()
    if fault_index is not None:
        return int(fault_index) < len(incident.fault_codes)
    if reading_index is not None:
        return int(reading_index) < len(incident.readings)
    return True


def build_diagnosis(incident: Incident, provider: DiagnosisProvider) -> DiagnosisRecord:
    response = provider.diagnose(incident)
    if not response.request_reference or not response.model_id:
        raise ProviderFailure("Provider response lacks a request reference or model ID")
    try:
        diagnosis = Diagnosis.model_validate(json.loads(response.raw_response))
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise ProviderFailure("Provider returned an invalid diagnosis") from exc
    if any(not _evidence_exists(incident, item.field) for item in diagnosis.supporting_evidence):
        raise ProviderFailure("Provider cited evidence absent from the incident")
    return DiagnosisRecord(
        id=str(uuid4()),
        incident_id=incident.id,
        incident=incident,
        diagnosis=diagnosis,
        created_at=datetime.now(timezone.utc),
        request_reference=response.request_reference,
        model_id=response.model_id,
        provider_kind=response.provider_kind,
        raw_response=response.raw_response,
    )
