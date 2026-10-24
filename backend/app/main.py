"""Local API with durable diagnosis, confirmation, and evaluation records."""

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .db import (
    confirmed_evaluation, connection, count_rows, get_diagnosis,
    initialize_database, list_diagnoses, list_repairs, save_diagnosis,
)
from .diagnosis import build_diagnosis
from .incidents import IncidentFileError, get_incident, list_incidents
from .live_monitor import live_monitor
from .provider import (
    DiagnosisProvider, ProviderFailure, ProviderTimeout, ProviderUnavailable,
    configured_provider,
)
from .schemas import (
    ConfirmedEvaluationReport, ConfirmRequest, ConfirmationRecord, DiagnoseRequest,
    DiagnosisRecord, Incident, Metrics, RepairRecord,
)
from .settings import CORS_ORIGIN, PROVIDER_MODE


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


app = FastAPI(title="Robo Medic API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[CORS_ORIGIN],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


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
    return configured_provider()


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
    try:
        record = build_diagnosis(selected, provider)
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderTimeout as exc:
        raise HTTPException(status_code=504, detail="Diagnosis provider timed out") from exc
    except ProviderFailure as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    save_diagnosis(record)
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
    return Metrics(
        incident_count=len(_incident_files_or_500()),
        diagnosis_count=count_rows("diagnoses"),
        confirmation_count=count_rows("confirmations"),
        provider_status="local_fixture" if PROVIDER_MODE == "local_fixture" else "not_configured",
        simulator_online=live_monitor.online,
    )

