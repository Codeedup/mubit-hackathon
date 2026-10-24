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
        signals = " ".join(incident.fault_codes).upper()
        if "WHEEL_STALL" in signals or "OBSTRUCTION" in signals:
            cause = "wheel obstruction"
            alternative = "motor power/driver path"
            next_check = "With power isolated, inspect the wheel and drivetrain for a physical blockage."
            uncertainty = "medium"
        elif "DRIVER" in signals or "UNDERVOLTAGE" in signals or "POWER" in signals:
            cause = "motor power/driver path"
            alternative = "wheel obstruction"
            next_check = "With a safe test setup, inspect the driver supply and motor wiring."
            uncertainty = "medium"
        elif "ENCODER" in signals or "REPORTING" in signals:
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
            if incident.fault_codes else
            {"field": "readings[0].value", "explanation": "The supplied reading alone does not confirm a cause."}
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
