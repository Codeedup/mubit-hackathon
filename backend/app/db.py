"""SQLite store for immutable diagnoses and inspected repair outcomes."""

import json
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .schemas import (
    ConfirmedEvaluation, ConfirmedEvaluationCase, ConfirmedEvaluationReport,
    DiagnosisRecord, RepairRecord,
)
from .settings import DB_PATH


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def initialize_database() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS diagnoses (
                id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL,
                diagnosis_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                request_reference TEXT,
                model_id TEXT,
                incident_json TEXT,
                raw_response TEXT,
                provider_kind TEXT
            );
            CREATE TABLE IF NOT EXISTS confirmations (
                id TEXT PRIMARY KEY,
                diagnosis_id TEXT NOT NULL UNIQUE REFERENCES diagnoses(id),
                incident_id TEXT NOT NULL,
                actual_cause TEXT NOT NULL,
                fix_performed TEXT NOT NULL,
                verifier TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                inspection_note TEXT,
                verification_kind TEXT
            );
            CREATE TABLE IF NOT EXISTS evaluations (
                id TEXT PRIMARY KEY,
                diagnosis_id TEXT REFERENCES diagnoses(id),
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        # Preserve an existing skeleton database when this contract is introduced.
        for table, additions in {
            "diagnoses": {
                "incident_json": "TEXT", "raw_response": "TEXT", "provider_kind": "TEXT"
            },
            "confirmations": {"inspection_note": "TEXT", "verification_kind": "TEXT"},
        }.items():
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for name, column_type in additions.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")


def count_rows(table: str) -> int:
    if table not in {"diagnoses", "confirmations", "evaluations"}:
        raise ValueError("Unsupported table")
    with connection() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def save_diagnosis(record: DiagnosisRecord) -> None:
    with connection() as conn:
        conn.execute(
            """INSERT INTO diagnoses
               (id, incident_id, diagnosis_json, created_at, request_reference,
                model_id, incident_json, raw_response, provider_kind)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id, record.incident_id, record.diagnosis.model_dump_json(),
                record.created_at.isoformat(), record.request_reference, record.model_id,
                record.incident.model_dump_json(), record.raw_response, record.provider_kind,
            ),
        )


def _diagnosis_from_row(row: sqlite3.Row) -> DiagnosisRecord:
    if not row["incident_json"] or not row["raw_response"] or not row["provider_kind"]:
        raise ValueError("Legacy diagnosis lacks its incident or provider trace")
    return DiagnosisRecord.model_validate({
        "id": row["id"],
        "incident_id": row["incident_id"],
        "incident": json.loads(row["incident_json"]),
        "diagnosis": json.loads(row["diagnosis_json"]),
        "created_at": row["created_at"],
        "request_reference": row["request_reference"],
        "model_id": row["model_id"],
        "provider_kind": row["provider_kind"],
        "raw_response": row["raw_response"],
    })


def get_diagnosis(diagnosis_id: str) -> DiagnosisRecord | None:
    with connection() as conn:
        row = conn.execute("SELECT * FROM diagnoses WHERE id = ?", (diagnosis_id,)).fetchone()
    return _diagnosis_from_row(row) if row is not None else None


def list_diagnoses(incident_id: str | None = None) -> list[DiagnosisRecord]:
    with connection() as conn:
        if incident_id is None:
            rows = conn.execute("SELECT * FROM diagnoses ORDER BY created_at DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM diagnoses WHERE incident_id = ? ORDER BY created_at DESC",
                (incident_id,),
            ).fetchall()
    return [_diagnosis_from_row(row) for row in rows]


def list_repairs(incident_id: str | None = None) -> list[RepairRecord]:
    query = """SELECT c.*, d.diagnosis_json, d.created_at AS diagnosis_created_at,
                      d.provider_kind, d.model_id
               FROM confirmations c JOIN diagnoses d ON d.id = c.diagnosis_id
               WHERE c.inspection_note IS NOT NULL
                 AND c.verification_kind IS NOT NULL"""
    parameters: tuple[str, ...] = ()
    if incident_id is not None:
        query += " AND c.incident_id = ?"
        parameters = (incident_id,)
    query += " ORDER BY d.created_at DESC, c.timestamp DESC"
    with connection() as conn:
        rows = conn.execute(query, parameters).fetchall()
    repairs = []
    for row in rows:
        predicted = json.loads(row["diagnosis_json"])["cause_label"]
        repairs.append(RepairRecord.model_validate({
            "id": row["id"], "diagnosis_id": row["diagnosis_id"],
            "incident_id": row["incident_id"], "actual_cause": row["actual_cause"],
            "fix_performed": row["fix_performed"], "inspection_note": row["inspection_note"],
            "verifier": row["verifier"], "timestamp": row["timestamp"],
            "verification_kind": row["verification_kind"],
            "predicted_cause": predicted,
            "diagnosis_created_at": row["diagnosis_created_at"],
            "provider_kind": row["provider_kind"], "model_id": row["model_id"],
            "matched": predicted == row["actual_cause"],
        }))
    return repairs


def confirmed_evaluation() -> ConfirmedEvaluationReport:
    repairs = [repair for repair in list_repairs() if repair.verification_kind == "inspection"]
    grouped: dict[tuple[str, str], list[RepairRecord]] = {}
    for repair in repairs:
        grouped.setdefault((repair.provider_kind, repair.model_id), []).append(repair)
    groups = []
    for (provider_kind, model_id), group_repairs in sorted(grouped.items()):
        latest_by_incident = {}
        for repair in group_repairs:
            latest_by_incident.setdefault(repair.incident_id, repair)
        cases = [ConfirmedEvaluationCase(
            diagnosis_id=repair.diagnosis_id,
            incident_id=repair.incident_id,
            predicted_cause=repair.predicted_cause,
            actual_cause=repair.actual_cause,
            matched=repair.matched,
        ) for repair in latest_by_incident.values()]
        matched = sum(case.matched for case in cases)
        groups.append(ConfirmedEvaluation(
            provider_kind=provider_kind, model_id=model_id,
            total=len(cases), confirmed_diagnosis_count=len(group_repairs),
            matched=matched, accuracy=matched / len(cases) if cases else None,
            cases=cases,
        ))
    return ConfirmedEvaluationReport(groups=groups)

