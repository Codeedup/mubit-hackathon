"""Load and atomically import immutable versioned incidents."""

import json
import os
import tempfile

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


def save_incident(incident: Incident) -> None:
    """A complete file becomes visible at once; never replace an existing case."""
    if get_incident(incident.id) is not None:
        raise FileExistsError(incident.id)
    INCIDENT_DIR.mkdir(parents=True, exist_ok=True)
    target = INCIDENT_DIR / f"{incident.id}.json"
    descriptor, temporary = tempfile.mkstemp(prefix=".import-", dir=INCIDENT_DIR)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(incident.model_dump_json(indent=2) + "\n")
        # Hard-link creation is atomic and fails if the destination exists.
        os.link(temporary, target)
    finally:
        os.unlink(temporary)

