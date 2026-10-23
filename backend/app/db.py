"""Small SQLite store; tables start empty."""

import sqlite3
from contextlib import contextmanager
from typing import Iterator

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
                model_id TEXT
            );
            CREATE TABLE IF NOT EXISTS confirmations (
                id TEXT PRIMARY KEY,
                diagnosis_id TEXT NOT NULL UNIQUE REFERENCES diagnoses(id),
                incident_id TEXT NOT NULL,
                actual_cause TEXT NOT NULL,
                fix_performed TEXT NOT NULL,
                verifier TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evaluations (
                id TEXT PRIMARY KEY,
                diagnosis_id TEXT REFERENCES diagnoses(id),
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


def count_rows(table: str) -> int:
    if table not in {"diagnoses", "confirmations", "evaluations"}:
        raise ValueError("Unsupported table")
    with connection() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

