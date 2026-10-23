"""Local API with real-time simulator fault detection, continual-learning diagnosis, and evaluation."""

import asyncio
import json
import sqlite3
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .db import connection, count_rows, initialize_database
from .diagnostics import diagnose_incident
from .incidents import IncidentFileError, get_incident, list_incidents
from .live_monitor import live_monitor
from .schemas import (
    ConfirmationRecord,
    ConfirmRequest,
    DiagnoseRequest,
    Diagnosis,
    DiagnosisRecord,
    EvaluationCaseResult,
    EvaluationSummary,
    Incident,
    Metrics,
)
from .settings import CORS_ORIGIN, EVAL_DIR, INCIDENT_DIR, SIMULATOR_URL


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    monitor_task = asyncio.create_task(live_monitor.run())
    try:
        yield
    finally:
        monitor_task.cancel()


app = FastAPI(title="Robo Medic API", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[CORS_ORIGIN, "http://127.0.0.1:5173", "http://localhost:8001"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


def _incident_files_or_500() -> list[Incident]:
    try:
        # Return newest incidents first so live pop-ups appear at the top of the queue
        return list(reversed(list_incidents()))
    except IncidentFileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _check_simulator_online() -> tuple[bool, dict[str, Any] | None]:
    try:
        req = urllib.request.Request(f"{SIMULATOR_URL}/api/packet", method="GET")
        with urllib.request.urlopen(req, timeout=0.6) as resp:
            pkt = json.loads(resp.read().decode("utf-8"))
            return True, pkt
    except Exception:
        return False, None


@app.get("/api/incidents", response_model=list[Incident])
def incidents() -> list[Incident]:
    return _incident_files_or_500()


@app.get("/api/incidents/{incident_id}", response_model=Incident)
def incident(incident_id: str) -> Incident:
    result = next((item for item in _incident_files_or_500() if item.id == incident_id), None)
    if result is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return result


@app.post("/api/incidents/clear")
def clear_incidents() -> dict[str, str]:
    if INCIDENT_DIR.exists():
        for path in INCIDENT_DIR.glob("*.json"):
            path.unlink(missing_ok=True)
    ans_file = EVAL_DIR / "answer_keys.json"
    if ans_file.exists():
        ans_file.unlink(missing_ok=True)
    with connection() as conn:
        conn.executescript(
            """
            DELETE FROM confirmations;
            DELETE FROM evaluations;
            DELETE FROM diagnoses;
            """
        )
    live_monitor.reset_tracking()
    live_monitor.incident_seq = 0
    return {"status": "cleared"}


@app.post("/api/diagnose", response_model=DiagnosisRecord)
def diagnose(request: DiagnoseRequest) -> DiagnosisRecord:
    try:
        inc = get_incident(request.incident_id)
    except IncidentFileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    diag, model_id = diagnose_incident(inc)
    now = datetime.now(timezone.utc)
    record = DiagnosisRecord(
        id=str(uuid4()),
        incident_id=inc.id,
        diagnosis=diag,
        created_at=now,
        request_reference=f"req-{uuid4().hex[:10]}",
        model_id=model_id,
    )
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO diagnoses (id, incident_id, diagnosis_json, created_at, request_reference, model_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.incident_id,
                record.diagnosis.model_dump_json(),
                record.created_at.isoformat(),
                record.request_reference,
                record.model_id,
            ),
        )
    return record


@app.get("/api/diagnoses", response_model=list[DiagnosisRecord])
def list_diagnoses() -> list[DiagnosisRecord]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, incident_id, diagnosis_json, created_at, request_reference, model_id
            FROM diagnoses
            ORDER BY created_at DESC
            """
        ).fetchall()
    out: list[DiagnosisRecord] = []
    for r in rows:
        out.append(
            DiagnosisRecord(
                id=r["id"],
                incident_id=r["incident_id"],
                diagnosis=Diagnosis.model_validate(json.loads(r["diagnosis_json"])),
                created_at=datetime.fromisoformat(r["created_at"]),
                request_reference=r["request_reference"],
                model_id=r["model_id"],
            )
        )
    return out


@app.get("/api/confirmations", response_model=list[ConfirmationRecord])
def list_confirmations() -> list[ConfirmationRecord]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, diagnosis_id, incident_id, actual_cause, fix_performed, verifier, timestamp
            FROM confirmations
            ORDER BY timestamp DESC
            """
        ).fetchall()
    return [
        ConfirmationRecord(
            id=r["id"],
            diagnosis_id=r["diagnosis_id"],
            incident_id=r["incident_id"],
            actual_cause=r["actual_cause"],
            fix_performed=r["fix_performed"],
            verifier=r["verifier"],
            timestamp=datetime.fromisoformat(r["timestamp"]),
        )
        for r in rows
    ]


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
                    record.id,
                    record.diagnosis_id,
                    record.incident_id,
                    record.actual_cause,
                    record.fix_performed,
                    record.verifier,
                    record.timestamp.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Diagnosis already confirmed") from exc
    return record


@app.post("/api/evaluate", response_model=EvaluationSummary)
def evaluate_suite() -> EvaluationSummary:
    all_incidents = _incident_files_or_500()
    answer_file = EVAL_DIR / "answer_keys.json"
    answer_keys: dict[str, Any] = {}
    if answer_file.exists():
        try:
            answer_keys = json.loads(answer_file.read_text(encoding="utf-8"))
        except Exception:
            answer_keys = {}

    results: list[EvaluationCaseResult] = []
    matched = 0
    for inc in all_incidents:
        expected_info = answer_keys.get(inc.id, {})
        expected_label = str(expected_info.get("expected_cause_label", "live-telemetry-anomaly"))
        expected_fault = str(expected_info.get("expected_fault", "")).lower()
        expected_comp = str(expected_info.get("expected_component", "")).lower()

        diag, _ = diagnose_incident(inc)
        pred_lower = diag.cause_label.lower()
        is_match = bool(
            (expected_fault and expected_fault in pred_lower)
            or (expected_comp and expected_comp in pred_lower and expected_fault in pred_lower)
            or (expected_label.lower() == pred_lower)
        )
        if is_match:
            matched += 1
        results.append(
            EvaluationCaseResult(
                incident_id=inc.id,
                expected_cause_label=expected_label,
                predicted_cause_label=diag.cause_label,
                matched=is_match,
                uncertainty=diag.uncertainty,
            )
        )

    total = len(results)
    accuracy = round((matched / total * 100.0) if total else 0.0, 1)
    summary = EvaluationSummary(
        id=str(uuid4()),
        total_cases=total,
        matched_cases=matched,
        accuracy_pct=accuracy,
        results=results,
        created_at=datetime.now(timezone.utc),
    )
    with connection() as conn:
        conn.execute(
            "INSERT INTO evaluations (id, diagnosis_id, result_json, created_at) VALUES (?, ?, ?, ?)",
            (summary.id, None, summary.model_dump_json(), summary.created_at.isoformat()),
        )
    return summary


@app.get("/api/evaluations", response_model=list[EvaluationSummary])
def list_evaluations() -> list[EvaluationSummary]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT result_json FROM evaluations ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
    out: list[EvaluationSummary] = []
    for r in rows:
        try:
            out.append(EvaluationSummary.model_validate(json.loads(r["result_json"])))
        except Exception:
            continue
    return out


@app.get("/api/simulator/status")
def simulator_status() -> dict[str, Any]:
    online, pkt = _check_simulator_online()
    return {
        "online": online,
        "simulator_url": SIMULATOR_URL,
        "latest_packet": pkt,
    }


def _post_sim_cmd(payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{SIMULATOR_URL}/api/command",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


@app.post("/api/simulator/command")
async def send_simulator_command(cmd: dict[str, Any]) -> dict[str, Any]:
    try:
        # Special composite software fix for mechanical motor jam:
        # Drive in reverse (>30% PWM) for 0.5s to clear the jam in simulator physics, then restore 150 RPM target
        if cmd.get("action") == "unjam_reverse":
            target = str(cmd.get("target", "n20_fl"))
            val = float(cmd.get("value", -0.6))
            await asyncio.to_thread(
                _post_sim_cmd,
                {
                    "type": "command",
                    "target": target,
                    "action": "set_pwm",
                    "value": val,
                    "reason": cmd.get("reason", "Reverse drive to clear mechanical jam"),
                },
            )
            await asyncio.sleep(0.55)
            res = await asyncio.to_thread(
                _post_sim_cmd,
                {
                    "type": "command",
                    "target": target,
                    "action": "set_target_rpm",
                    "value": 150.0,
                    "reason": "Resume normal PID target RPM after clearing jam",
                },
            )
            return {
                "type": "ack",
                "ok": True,
                "message": f"Pulsed {target} in reverse ({val} PWM for 0.5s) -> jam cleared & resumed 150 RPM ({res.get('message')})",
            }
        return await asyncio.to_thread(_post_sim_cmd, cmd)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Failed to send command to simulator: {exc}") from exc


@app.get("/api/metrics", response_model=Metrics)
def metrics() -> Metrics:
    conf_count = count_rows("confirmations")
    eval_count = count_rows("evaluations")
    latest_acc: float | None = None
    with connection() as conn:
        row = conn.execute("SELECT result_json FROM evaluations ORDER BY created_at DESC LIMIT 1").fetchone()
        if row:
            try:
                latest_acc = float(json.loads(row["result_json"]).get("accuracy_pct"))
            except Exception:
                latest_acc = None
    sim_online, _ = _check_simulator_online()
    return Metrics(
        incident_count=len(_incident_files_or_500()),
        diagnosis_count=count_rows("diagnoses"),
        confirmation_count=conf_count,
        evaluation_count=eval_count,
        latest_accuracy_pct=latest_acc,
        provider_status="ready",
        task_status="ready",
        adapter_status="learning" if conf_count > 0 else "ready",
        simulator_online=sim_online,
    )
