"""Local API with durable diagnosis, confirmation, and evaluation records."""

import asyncio
import json
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .db import (
    claim_request, confirmed_evaluation, connection, count_rows, get_diagnosis,
    initialize_database, list_diagnoses, list_repairs, save_diagnosis,
)
from .diagnosis import build_diagnosis
from .incidents import IncidentFileError, get_incident, list_incidents, save_incident
from .demo import SCENARIOS, demo_incident
from .evaluate import evaluate_synthetic
from . import mubit, settings
from .live_monitor import live_monitor
from .provider import (
    DiagnosisProvider, ProviderFailure, ProviderTimeout, ProviderUnavailable,
    configured_provider,
)
from .schemas import (
    ConfirmedEvaluationReport, ConfirmRequest, ConfirmationRecord, DiagnoseRequest,
    DiagnosisRecord, FeedbackRequest, Incident, Metrics, RepairRecord,
)
from .settings import CORS_ORIGIN, MUBIT_API_KEY, MUBIT_MODEL, PROVIDER_MODE


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    monitor_task = asyncio.create_task(live_monitor.run())
    try:
        yield
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Robo Medic API", version="1.0.0", lifespan=lifespan,
              description="Local robot fault diagnosis, evidence, and technician outcomes.")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=[CORS_ORIGIN],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def local_mutations(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and origin not in {CORS_ORIGIN, str(request.base_url).rstrip("/")}:
            return JSONResponse({"detail": "This local app does not accept writes from that origin."}, status_code=403)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 2 * 1024 * 1024:
                return JSONResponse({"detail": "Request exceeds the 2 MB limit."}, status_code=413)
        request._body = bytes(body)
    return await call_next(request)


@app.get("/api/health")
def health() -> dict:
    with connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok", "version": app.version, "provider": PROVIDER_MODE}


@app.get("/api/setup")
def setup() -> dict:
    return {"version": app.version, "provider": PROVIDER_MODE, "model": MUBIT_MODEL,
            "inference_key_configured": bool(MUBIT_API_KEY),
            "management_key_configured": bool(settings.MUBIT_MANAGEMENT_KEY),
            "project_id": settings.MUBIT_PROJECT_ID, "task_id": settings.MUBIT_TASK_ID,
            "simulator_url": settings.SIMULATOR_URL,
            "frontend_built": (settings.FRONTEND_DIST / "index.html").exists()}


@app.post("/api/incidents", response_model=Incident, status_code=201)
def import_incident(incident: Incident) -> Incident:
    try:
        save_incident(incident)
    except FileExistsError as exc:
        raise HTTPException(409, "A case with this ID already exists. Use a new ID for a revision.") from exc
    except (OSError, IncidentFileError) as exc:
        raise HTTPException(500, "The incident could not be saved. Check the data directory.") from exc
    return incident


@app.post("/api/demo/{scenario}", response_model=Incident, status_code=201)
def create_demo(scenario: str) -> Incident:
    if scenario not in SCENARIOS:
        raise HTTPException(404, "Unknown demo scenario")
    return import_incident(demo_incident(scenario))


@app.get("/api/export")
def export_workspace() -> JSONResponse:
    records = list_diagnoses()
    current = {item.id: item for item in _incident_files_or_500()}
    for record in records:
        current.setdefault(record.incident_id, record.incident)
    return JSONResponse(jsonable_encoder({
        "schema_version": "1.0", "exported_at": datetime.now(timezone.utc),
        "incidents": list(current.values()), "diagnoses": records, "outcomes": list_repairs(),
    }), headers={"Content-Disposition": 'attachment; filename="robo-medic-workspace.json"'})


@app.get("/api/evaluation/synthetic")
def synthetic_evaluation(split: str = "held_out", provider_kind: str = "local_fixture") -> dict:
    if split not in {"development", "held_out"} or provider_kind not in {"local_fixture", "mubit"}:
        raise HTTPException(422, "Choose a supported evaluation split and provider.")
    return evaluate_synthetic(settings.ROOT / "data/evaluation/answer_keys.synthetic.json", split, provider_kind)


@app.get("/api/mubit/status")
def mubit_status() -> dict:
    try:
        return mubit.task_status()
    except mubit.MubitManagementError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/diagnoses/{diagnosis_id}/feedback")
def feedback_status(diagnosis_id: str) -> dict:
    if get_diagnosis(diagnosis_id) is None:
        raise HTTPException(404, "Diagnosis not found")
    return mubit.feedback_status(diagnosis_id)


@app.post("/api/diagnoses/{diagnosis_id}/feedback")
def submit_feedback(diagnosis_id: str, request: FeedbackRequest) -> dict:
    try:
        return mubit.submit_feedback(diagnosis_id, request.call_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except mubit.MubitManagementError as exc:
        raise HTTPException(502, str(exc)) from exc


def _incident_files_or_500() -> list[Incident]:
    try:
        return list_incidents()
    except IncidentFileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/incidents", response_model=list[Incident])
def incidents() -> list[Incident]:
    return _incident_files_or_500()


@app.get("/api/incidents/{incident_id}", response_model=Incident)
def incident(incident_id: str) -> Incident:
    result = next((item for item in _incident_files_or_500() if item.id == incident_id), None)
    if result is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return result


def provider_dependency() -> DiagnosisProvider:
    try:
        return configured_provider()
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/diagnose", response_model=DiagnosisRecord, status_code=201)
def diagnose(
    request: DiagnoseRequest,
    provider: DiagnosisProvider = Depends(provider_dependency),
) -> DiagnosisRecord:
    try:
        selected = get_incident(request.incident_id)
    except IncidentFileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if selected is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    if request.request_id:
        try:
            previous = claim_request(request.request_id, selected.id)
            if previous:
                return previous
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    try:
        record = build_diagnosis(selected, provider)
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderTimeout as exc:
        raise HTTPException(status_code=504, detail="Diagnosis provider timed out") from exc
    except ProviderFailure as exc:
        logging.getLogger(__name__).error("Diagnosis provider failure: %s", json.dumps({
            "incident_id": selected.id, "reason": str(exc),
            "request_reference": exc.request_reference, **exc.trace,
        }, default=str))
        reference = f" (request {exc.request_reference})" if exc.request_reference else ""
        raise HTTPException(status_code=502, detail=f"{exc}{reference}") from exc
    save_diagnosis(record)
    if request.request_id:
        with connection() as conn:
            conn.execute("UPDATE diagnosis_requests SET diagnosis_id = ? WHERE request_id = ?", (record.id, request.request_id))
    return record


@app.get("/api/diagnoses", response_model=list[DiagnosisRecord])
def diagnoses(incident_id: str | None = None) -> list[DiagnosisRecord]:
    return list_diagnoses(incident_id)


@app.get("/api/diagnoses/{diagnosis_id}", response_model=DiagnosisRecord)
def diagnosis(diagnosis_id: str) -> DiagnosisRecord:
    result = get_diagnosis(diagnosis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Diagnosis not found")
    return result


@app.post("/api/confirm", response_model=ConfirmationRecord)
def confirm(request: ConfirmRequest) -> ConfirmationRecord:
    with connection() as conn:
        diagnosis = conn.execute(
            "SELECT incident_id, incident_json FROM diagnoses WHERE id = ?", (request.diagnosis_id,)
        ).fetchone()
        if diagnosis is None:
            raise HTTPException(status_code=404, detail="Diagnosis not found")
        if diagnosis["incident_id"] != request.incident_id:
            raise HTTPException(status_code=409, detail="Diagnosis belongs to another incident")
        if not diagnosis["incident_json"]:
            raise HTTPException(status_code=409, detail="Diagnosis lacks an incident snapshot")
        original_incident = Incident.model_validate_json(diagnosis["incident_json"])
        verification_kind = (
            "synthetic_simulation" if original_incident.source_type == "synthetic" else "inspection"
        )
        record = ConfirmationRecord(
            id=str(uuid4()), verification_kind=verification_kind, **request.model_dump()
        )
        try:
            conn.execute(
                """INSERT INTO confirmations
                   (id, diagnosis_id, incident_id, actual_cause, fix_performed,
                    inspection_note, verifier, timestamp, verification_kind)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.id, record.diagnosis_id, record.incident_id,
                    record.actual_cause, record.fix_performed, record.inspection_note,
                    record.verifier,
                    record.timestamp.isoformat(),
                    record.verification_kind,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Diagnosis already confirmed") from exc
    return record


@app.get("/api/repairs", response_model=list[RepairRecord])
def repairs(incident_id: str | None = None) -> list[RepairRecord]:
    return list_repairs(incident_id)


@app.get("/api/evaluation/confirmed", response_model=ConfirmedEvaluationReport)
def evaluation_confirmed() -> ConfirmedEvaluationReport:
    return confirmed_evaluation()


@app.get("/api/metrics", response_model=Metrics)
def metrics() -> Metrics:
    provider_status = PROVIDER_MODE if PROVIDER_MODE != "unavailable" else "not_configured"
    if PROVIDER_MODE == "mubit" and (not MUBIT_API_KEY or not MUBIT_MODEL):
        provider_status = "missing_credentials"
    return Metrics(
        incident_count=len(_incident_files_or_500()),
        diagnosis_count=count_rows("diagnoses"),
        confirmation_count=count_rows("confirmations"),
        provider_status=provider_status,
        simulator_online=live_monitor.online,
    )


# API routes are registered first so missing API paths always return JSON 404s.
if settings.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=settings.FRONTEND_DIST / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def frontend():
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        return JSONResponse({"detail": "Build the interface with npm ci and npm run build in frontend/."}, status_code=503)
    return FileResponse(index)


@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    return FileResponse(settings.ROOT / "frontend/public/favicon.svg", media_type="image/svg+xml")

