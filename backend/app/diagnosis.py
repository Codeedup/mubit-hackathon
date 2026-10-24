"""Parse provider output and keep only diagnoses grounded in the supplied case."""

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from .provider import DiagnosisProvider, ProviderFailure
from .schemas import CauseLabel, Diagnosis, DiagnosisRecord, Incident


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


_LABELS = {"wheel obstruction", "motor power/driver path", "encoder/reporting fault", "unknown"}


def parse_cause_label(raw_text: str) -> CauseLabel:
    label = raw_text.strip().lower()
    if label not in _LABELS:
        raise ValueError("Provider reply is not exactly one supported cause label")
    return label  # type: ignore[return-value]


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _advisory(incident: Incident, label: CauseLabel) -> Diagnosis:
    readings = {reading.sensor: (index, reading.value) for index, reading in enumerate(incident.readings)}

    def numeric(sensor: str) -> float | None:
        item = readings.get(sensor)
        return _number(item[1]) if item else None

    clue: tuple[int, str] | None = None
    if label == "wheel obstruction":
        for side in ("left", "right"):
            if numeric(f"{side}_wheel_speed") == 0 and (numeric(f"{side}_motor_current") or 0) >= 1:
                clue = (readings[f"{side}_motor_current"][0], "High motor current with no reported wheel speed is a clue to resistance, not proof of blockage.")
                break
        if clue is None:
            for motor in ("n20_fl", "n20_fr", "n20_rl", "n20_rr"):
                if ((numeric(f"{motor}.target_rpm") or 0) > 1 and numeric(f"{motor}.rpm") == 0
                        and (numeric(f"{motor}.current_a") or 0) >= 0.5):
                    clue = (readings[f"{motor}.current_a"][0], "Current with commanded but absent rotation is a clue to resistance, not proof of blockage.")
                    break
        alternative = "motor power/driver path"
        next_check = "With power isolated, inspect the wheel and drivetrain for a physical blockage."
    elif label == "motor power/driver path":
        supply = numeric("driver_supply")
        if supply is not None and supply < 5:
            clue = (readings["driver_supply"][0], "The low driver supply is a power-path clue, not a verified failed component.")
        elif readings.get("driver_output_state", (None, None))[1] == "inactive":
            clue = (readings["driver_output_state"][0], "The inactive driver output is a clue, not a verified failed component.")
        elif numeric("motor_terminal_voltage") is not None and numeric("motor_terminal_voltage") < 1 and supply is not None and supply > 5:
            clue = (readings["motor_terminal_voltage"][0], "Low motor terminal voltage despite supply is a driver-path clue.")
        alternative = "wheel obstruction"
        next_check = "With a safe test setup, measure driver supply and motor terminal voltage, then inspect wiring."
    elif label == "encoder/reporting fault":
        motion = readings.get("observed_wheel_motion", (None, None))[1]
        ticks = numeric("reported_encoder_ticks")
        if motion in {"moving", "rotating"} and ticks is not None and ticks <= 1:
            clue = (readings["reported_encoder_ticks"][0], "Reported ticks disagree with observed motion; this is a reporting clue, not a verified encoder defect.")
        alternative = "wheel obstruction"
        next_check = "Inspect encoder wiring and compare reported ticks with independently observed wheel movement."
    else:
        alternative = "wheel obstruction or motor power/driver path"
        next_check = "Obtain an independent motion observation and measure motor current or driver supply."

    if label != "unknown" and clue is None:
        label = "unknown"
        alternative = "The model label lacks a supporting clue in the supplied readings."
        next_check = "Obtain an independent motion observation and measure motor current or driver supply."
    if clue is None:
        clue = (0, "This supplied reading does not distinguish a cause; another measurement is needed.")
    return Diagnosis(
        cause_label=label,
        supporting_evidence=[{"field": f"readings[{clue[0]}].value", "explanation": clue[1]}],
        alternative=alternative, next_check=next_check,
        uncertainty="high" if label == "unknown" else "medium",
    )


def build_diagnosis(incident: Incident, provider: DiagnosisProvider) -> DiagnosisRecord:
    response = provider.diagnose(incident)
    if not response.request_reference or not response.model_id:
        raise ProviderFailure("Provider response lacks a request reference or model ID")
    if response.provider_kind == "mubit":
        try:
            model_label = parse_cause_label(response.raw_response)
        except ValueError as exc:
            raise ProviderFailure(str(exc), response.request_reference,
                                  {"raw_text_length": len(response.raw_response)}) from exc
        diagnosis = _advisory(incident, model_label)
        advisory_source = "application_rules"
    else:
        try:
            diagnosis = Diagnosis.model_validate(json.loads(response.raw_response))
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise ProviderFailure("Provider returned an invalid diagnosis", response.request_reference) from exc
        model_label = diagnosis.cause_label
        advisory_source = "local_fixture"
    if any(not _evidence_exists(incident, item.field) for item in diagnosis.supporting_evidence):
        raise ProviderFailure("Provider cited evidence absent from the incident", response.request_reference)
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
        model_label=model_label,
        advisory_source=advisory_source,
    )
