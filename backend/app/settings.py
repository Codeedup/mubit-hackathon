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
CAPTURED_KEYS_DIR = _resolve_path(os.getenv("ROBO_MEDIC_CAPTURED_KEYS_DIR", "data/evaluation/captured"))
CORS_ORIGIN = os.getenv("ROBO_MEDIC_CORS_ORIGIN", "http://localhost:5173")
SIMULATOR_URL = os.getenv("ROBO_MEDIC_SIMULATOR_URL", "http://127.0.0.1:8001").rstrip("/")
PROVIDER_MODE = os.getenv("ROBO_MEDIC_PROVIDER", "local_fixture")
if PROVIDER_MODE not in {"unavailable", "local_fixture", "mubit"}:
    raise ValueError("ROBO_MEDIC_PROVIDER must be unavailable, local_fixture, or mubit")
MUBIT_API_KEY = os.getenv("MUBIT_API_KEY", "").strip()
MUBIT_MODEL = os.getenv("MUBIT_MODEL", "gemini-3.8-flash").strip()
MUBIT_BASE_URL = os.getenv("MUBIT_BASE_URL", "https://api.mubit.ai/gemini").rstrip("/")
MUBIT_MANAGEMENT_KEY = os.getenv("MUBIT_MANAGEMENT_KEY", "").strip()
MUBIT_MANAGEMENT_URL = os.getenv("MUBIT_MANAGEMENT_URL", "https://api.mubit.ai").rstrip("/")
MUBIT_PROJECT_ID = os.getenv("MUBIT_PROJECT_ID", "").strip()
MUBIT_TASK_ID = os.getenv("MUBIT_TASK_ID", "").strip()
FRONTEND_DIST = ROOT / "frontend" / "dist"

