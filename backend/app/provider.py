"""Provider boundary and an explicitly local, deterministic demo fixture.

No external API behavior is assumed here. A Mubit adapter can implement the same
protocol after its supported route and response fields are verified.
"""

import json
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import uuid4

from .schemas import Incident
from .settings import PROVIDER_MODE


TASK_INSTRUCTIONS = """Diagnose only from the supplied incident JSON. Return one JSON object
with cause_label, supporting_evidence [{field, explanation}], alternative,
next_check, and uncertainty. The cause_label must be wheel obstruction,
motor power/driver path, encoder/reporting fault, or unknown.
Every evidence field must identify an existing incident field. Do not invent
measurements or imply that a next check has been performed. If the cause is
unclear, use unknown and request a useful inspection or measurement."""


class ProviderUnavailable(Exception):
    pass


class ProviderFailure(Exception):
    pass


class ProviderTimeout(Exception):
    pass


@dataclass(frozen=True)
class ProviderResponse:
    raw_response: str
    request_reference: str
    model_id: str
    provider_kind: Literal["local_fixture", "mubit"]


class DiagnosisProvider(Protocol):
    def diagnose(self, incident: Incident) -> ProviderResponse: ...


class UnavailableProvider:
    def diagnose(self, incident: Incident) -> ProviderResponse:
        raise ProviderUnavailable("Diagnosis provider is not configured")


class LocalFixtureProvider:
    """Rule-based fixture for exercising storage and API flow without credentials."""

    def diagnose(self, incident: Incident) -> ProviderResponse:
        signals = " ".join(incident.fault_codes).upper() if incident.source_type != "synthetic" else ""
        readings = {reading.sensor: (index, reading.value)
                    for index, reading in enumerate(incident.readings)}

        def number(sensor: str) -> float | None:
            item = readings.get(sensor)
            value = item[1] if item else None
            return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

        evidence_index: int | None = None
        motion = readings.get("observed_wheel_motion")
        ticks = number("reported_encoder_ticks")
        driver_supply = number("driver_supply")
        driver_output = readings.get("driver_output_state")
        terminal_voltage = number("motor_terminal_voltage")
        stalled_wheel = next((name for name in ("left", "right")
                              if number(f"{name}_wheel_speed") == 0
                              and (number(f"{name}_motor_current") or 0) >= 1), None)
        stalled_motor = next((name for name in ("n20_fl", "n20_fr", "n20_rl", "n20_rr")
                              if (number(f"{name}.target_rpm") or 0) > 1
                              and number(f"{name}.rpm") == 0
                              and (number(f"{name}.current_a") or 0) >= 0.5), None)
        if motion and motion[1] in {"moving", "rotating"} and ticks is not None and ticks <= 1:
            cause = "encoder/reporting fault"
            alternative = "wheel obstruction"
            next_check = "Inspect encoder wiring and compare reported ticks with observed wheel movement."
            uncertainty = "medium"
            evidence_index = readings["reported_encoder_ticks"][0]
        elif ((driver_supply is not None and driver_supply < 5)
              or (driver_output is not None and driver_output[1] == "inactive")
              or (terminal_voltage is not None and terminal_voltage < 1
                  and driver_supply is not None and driver_supply > 5)):
            cause = "motor power/driver path"
            alternative = "wheel obstruction"
            next_check = "With a safe test setup, inspect the driver supply and motor wiring."
            uncertainty = "medium"
            evidence_index = (readings.get("driver_supply") or driver_output
                              or readings["motor_terminal_voltage"])[0]
        elif stalled_wheel or stalled_motor:
            cause = "wheel obstruction"
            alternative = "motor power/driver path"
            next_check = "With power isolated, inspect the wheel and drivetrain for a physical blockage."
            uncertainty = "medium"
            name = (f"{stalled_wheel}_motor_current" if stalled_wheel
                    else f"{stalled_motor}.current_a")
            evidence_index = readings[name][0]
        elif "WHEEL_STALL" in signals or "OBSTRUCTION" in signals:
            cause = "wheel obstruction"
            alternative = "motor power/driver path"
            next_check = "With power isolated, inspect the wheel and drivetrain for a physical blockage."
            uncertainty = "medium"
        elif any(token in signals for token in ("DRIVER", "UNDERVOLTAGE", "POWER", "OPEN_CIRCUIT", "BURNED_OUT", "DISCONNECTED", "RAIL_SAG")):
            cause = "motor power/driver path"
            alternative = "wheel obstruction"
            next_check = "With a safe test setup, inspect the driver supply and motor wiring."
            uncertainty = "medium"
        elif any(token in signals for token in ("ENCODER", "REPORTING", "ERR_ENC_")):
            cause = "encoder/reporting fault"
            alternative = "wheel obstruction"
            next_check = "Inspect encoder wiring and compare reported ticks with observed wheel movement."
            uncertainty = "medium"
        else:
            cause = "unknown"
            alternative = "wheel obstruction or motor power/driver path"
            next_check = "Inspect the drivetrain and obtain a supported motor or encoder reading."
            uncertainty = "high"

        evidence = (
            {"field": "fault_codes[0]", "explanation": "The supplied fault code is a diagnostic clue, not confirmation."}
            if evidence_index is None and incident.fault_codes and incident.source_type != "synthetic" else
            {"field": f"readings[{evidence_index or 0}].value", "explanation": "The supplied telemetry is a diagnostic clue, not confirmation."}
        )
        result = {
            "cause_label": cause,
            "supporting_evidence": [evidence],
            "alternative": alternative,
            "next_check": next_check,
            "uncertainty": uncertainty,
        }
        return ProviderResponse(
            raw_response=json.dumps(result),
            request_reference=f"local-fixture:{uuid4()}",
            model_id="local-rule-fixture-v1",
            provider_kind="local_fixture",
        )


def configured_provider() -> DiagnosisProvider:
    if PROVIDER_MODE == "local_fixture":
        return LocalFixtureProvider()
    return UnavailableProvider()
