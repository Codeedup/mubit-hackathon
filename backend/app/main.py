"""Local API skeleton. Provider integration is intentionally absent."""

import sqlite3
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .db import connection, count_rows, initialize_database
from .incidents import IncidentFileError, get_incident, list_incidents
from .schemas import ConfirmRequest, ConfirmationRecord, DiagnoseRequest, Incident, Metrics
from .settings import CORS_ORIGIN


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    yield


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


@app.post("/api/diagnose")
def diagnose(_request: DiagnoseRequest) -> None:
    raise HTTPException(status_code=503, detail="Diagnosis service is not configured")


@app.post("/api/confirm", response_model=ConfirmationRecord)
def confirm(request: ConfirmRequest) -> ConfirmationRecord:
    try:
        incident_exists = get_incident(request.incident_id) is not None
    except IncidentFileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not incident_exists:
        raise HTTPException(status_code=404, detail="Incident not found")
    with connection() as conn:
        diagnosis = conn.execute(
            "SELECT incident_id FROM diagnoses WHERE id = ?", (request.diagnosis_id,)
        ).fetchone()
        if diagnosis is None:
            raise HTTPException(status_code=404, detail="Diagnosis not found")
        if diagnosis["incident_id"] != request.incident_id:
            raise HTTPException(status_code=409, detail="Diagnosis belongs to another incident")
        record = ConfirmationRecord(id=str(uuid4()), **request.model_dump())
        try:
            conn.execute(
                """INSERT INTO confirmations
                   (id, diagnosis_id, incident_id, actual_cause, fix_performed, verifier, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.id, record.diagnosis_id, record.incident_id,
                    record.actual_cause, record.fix_performed, record.verifier,
                    record.timestamp.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Diagnosis already confirmed") from exc
    return record


@app.get("/api/metrics", response_model=Metrics)
def metrics() -> Metrics:
    return Metrics(
        incident_count=len(_incident_files_or_500()),
        diagnosis_count=count_rows("diagnoses"),
        confirmation_count=count_rows("confirmations"),
    )

