"""Optional Mubit management integration. No inference or automatic training."""

import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from threading import Lock

from . import settings
from .db import connection, get_diagnosis, list_repairs
from .provider import serialize_incident


class MubitManagementError(Exception):
    pass


_feedback_lock = Lock()


def management_request(path: str, payload: dict | None = None, key: str = "") -> dict:
    if not settings.MUBIT_MANAGEMENT_KEY:
        raise MubitManagementError("Add MUBIT_MANAGEMENT_KEY to .env and restart to use this feature.")
    headers = {"Authorization": f"Bearer {settings.MUBIT_MANAGEMENT_KEY}", "Accept": "application/json"}
    if payload is not None:
        headers.update({"Content-Type": "application/json", "Idempotency-Key": key})
    request = Request(
        f"{settings.MUBIT_MANAGEMENT_URL}/api/v1/{path}", headers=headers,
        data=json.dumps(payload).encode() if payload is not None else None,
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
        if not isinstance(result, dict):
            raise ValueError("Expected an object")
        return result
    except HTTPError as exc:
        exc.close()
        raise MubitManagementError(
            f"Mubit management returned HTTP {exc.code}. Check the key's role, project scope, and console call ID."
        ) from exc
    except (OSError, URLError, ValueError) as exc:
        raise MubitManagementError("Mubit management could not be reached or returned an invalid response. Try again later.") from exc


def task_status() -> dict:
    checked = datetime.now(timezone.utc).isoformat()
    if not settings.MUBIT_MANAGEMENT_KEY or not settings.MUBIT_TASK_ID:
        return {"status": "not_configured", "checked_at": checked,
                "message": "Connect a management key and task ID in Setup to read live adapter status."}
    task = management_request(f"tasks/{quote(settings.MUBIT_TASK_ID, safe='')}")
    if (task.get("id") != settings.MUBIT_TASK_ID or not task.get("name") or not task.get("stage")
            or not isinstance(task.get("rows_count"), int)):
        raise MubitManagementError("Mubit returned an incomplete task record. Check the task ID and service version.")
    if settings.MUBIT_PROJECT_ID and task.get("project") != settings.MUBIT_PROJECT_ID:
        raise MubitManagementError("This task belongs to a different project. Check MUBIT_PROJECT_ID.")
    versions = management_request(f"tasks/{quote(settings.MUBIT_TASK_ID, safe='')}/versions?limit=20")
    if not isinstance(versions.get("data"), list):
        raise MubitManagementError("Mubit returned an incomplete version list. Try again later.")
    return {"status": "connected", "checked_at": checked,
            "task": {key: task.get(key) for key in (
                "id", "name", "project", "stage", "rows_count", "holdout_count", "active_version", "recommendation")},
            "versions": [{key: version.get(key) for key in (
                "id", "version_number", "status", "score", "base_model", "created_at")}
                for version in versions.get("data", []) if isinstance(version, dict)]}


def feedback_status(diagnosis_id: str) -> dict:
    with connection() as conn:
        row = conn.execute("SELECT * FROM mubit_feedback WHERE diagnosis_id = ?", (diagnosis_id,)).fetchone()
    return {"configured": bool(settings.MUBIT_MANAGEMENT_KEY and settings.MUBIT_PROJECT_ID),
            "submission": dict(row) if row else None}


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    return []


def submit_feedback(diagnosis_id: str, call_id: str) -> dict:
    # The launcher uses one server process. Serialize writes so a double-click
    # cannot race a second call link or overwrite a rating from another outcome.
    with _feedback_lock:
        return _submit_feedback(diagnosis_id, call_id)


def _submit_feedback(diagnosis_id: str, call_id: str) -> dict:
    existing = feedback_status(diagnosis_id)
    if existing["submission"]:
        if existing["submission"]["call_id"] != call_id:
            raise ValueError("This diagnosis already has feedback for another call.")
        return existing["submission"]
    with connection() as conn:
        if conn.execute("SELECT 1 FROM mubit_feedback WHERE call_id = ?", (call_id,)).fetchone():
            raise ValueError("This console call is already linked to a different diagnosis.")
    record = get_diagnosis(diagnosis_id)
    if record is None:
        raise LookupError("Diagnosis not found")
    if record.provider_kind != "mubit":
        raise ValueError("Only saved Mubit-routed calls can be submitted to Mubit.")
    repair = next((item for item in list_repairs(record.incident_id) if item.diagnosis_id == diagnosis_id), None)
    if repair is None:
        raise ValueError("Record an inspected or simulated outcome before submitting feedback.")
    if repair.actual_cause not in {"wheel obstruction", "motor power/driver path", "encoder/reporting fault", "unknown"}:
        raise ValueError("The confirmed cause must use the classifier's label set before it can be submitted.")
    if not settings.MUBIT_PROJECT_ID:
        raise ValueError("Set MUBIT_PROJECT_ID so feedback can be checked against the correct project.")
    call = management_request(f"calls/{quote(call_id, safe='')}")
    if call.get("id") != call_id or call.get("project") != settings.MUBIT_PROJECT_ID:
        raise ValueError("The selected call does not belong to the configured project.")
    if serialize_incident(record.incident) not in _strings(call.get("request")):
        raise ValueError("The console call's recorded input does not match this incident. No feedback was sent.")
    labels = [text.strip().lower() for text in _strings(call.get("response"))]
    if record.raw_response.strip().lower() not in labels:
        raise ValueError("The console call's reply does not match the saved model reply. No feedback was sent.")
    rating = "up" if record.model_label == repair.actual_cause else "down"
    result = management_request(f"calls/{quote(call_id, safe='')}/feedback", {
        "rating": rating, "correction": repair.actual_cause,
        "comment": f"Robo Medic {repair.verification_kind}: {repair.inspection_note}"[:500],
    }, key=f"robo-medic-{diagnosis_id}")
    if result.get("call_id") != call_id or result.get("rating") != rating or not result.get("id"):
        raise MubitManagementError("Mubit did not acknowledge the expected feedback. Retry with the same call ID.")
    submitted_at = datetime.now(timezone.utc).isoformat()
    with connection() as conn:
        conn.execute("INSERT OR IGNORE INTO mubit_feedback VALUES (?, ?, ?, ?, ?)",
                     (diagnosis_id, call_id, rating, result["id"], submitted_at))
    return feedback_status(diagnosis_id)["submission"]
