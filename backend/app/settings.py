import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


DB_PATH = _resolve_path(os.getenv("ROBO_MEDIC_DB_PATH", "backend/robo_medic.sqlite3"))
INCIDENT_DIR = _resolve_path(os.getenv("ROBO_MEDIC_INCIDENT_DIR", "data/incidents"))
CORS_ORIGIN = os.getenv("ROBO_MEDIC_CORS_ORIGIN", "http://localhost:5173")
PROVIDER_MODE = os.getenv("ROBO_MEDIC_PROVIDER", "unavailable")
if PROVIDER_MODE not in {"unavailable", "local_fixture"}:
    raise ValueError("ROBO_MEDIC_PROVIDER must be unavailable or local_fixture")

