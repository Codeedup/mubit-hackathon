"""Load team-authored, versioned incident JSON. No records are bundled."""

import json

from pydantic import ValidationError

from .schemas import Incident
from .settings import INCIDENT_DIR


class IncidentFileError(Exception):
    pass


def list_incidents() -> list[Incident]:
    incidents: list[Incident] = []
    if not INCIDENT_DIR.exists():
        return incidents
    for path in sorted(INCIDENT_DIR.glob("*.json")):
        try:
            incident = Incident.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise IncidentFileError(f"Invalid incident file: {path.name}") from exc
        incidents.append(incident)
    ids = [incident.id for incident in incidents]
    if len(ids) != len(set(ids)):
        raise IncidentFileError("Duplicate incident IDs in data/incidents")
    return incidents


def get_incident(incident_id: str) -> Incident | None:
    return next((item for item in list_incidents() if item.id == incident_id), None)

