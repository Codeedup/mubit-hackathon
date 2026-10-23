# Robo Medic

Blank, local-first starting point for the Mubit Night Shift hackathon team. The browser shows three technician views, the API exposes the agreed route names, and SQLite starts with empty tables. No incidents, model responses, answer keys, provider calls, or credentials are included.

## Run locally

Requires Node.js 22+ and Python 3.10+.

**Backend (PowerShell, from the repository root):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

**Frontend (second terminal):**

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. FastAPI docs are at `http://localhost:8000/docs`. Vite proxies `/api` to port 8000. The backend allows the `http://localhost:5173` browser origin by default. Copy `.env.example` to `.env` to change the database path, incident directory, or CORS origin.

The backend creates `backend/robo_medic.sqlite3` with empty `diagnoses`, `confirmations`, and `evaluations` tables at startup. That database file is ignored by Git.

## Current API contract

| Method | Path | Baseline behavior |
| --- | --- | --- |
| `GET` | `/api/incidents` | Validated JSON incident files, or `[]` when none exist |
| `GET` | `/api/incidents/{id}` | One incident, or 404 |
| `POST` | `/api/diagnose` | Validates `{ "incident_id": "..." }`, then returns 503 `Diagnosis service is not configured` |
| `POST` | `/api/confirm` | Validates a technician outcome; saves only when the incident file and stored diagnosis exist |
| `GET` | `/api/metrics` | Local counts plus `not_configured`/`unavailable` provider status |

API errors use FastAPI's JSON `detail` field. Pydantic validation errors return 422. The baseline provides no route that writes diagnoses; that is part of the future provider work.

### Incident files

Place one versioned `.json` file per incident in `data/incidents/`. The API validates these top-level fields: `id`, `robot_type`, `time_window`, `commanded_action`, `readings`, `fault_codes`, `technician_note`, and `source_type` (`synthetic`, `measured`, or `operator-observed`). IDs must be unique. Invalid files produce a clear API error; they are not silently skipped.

**Owners A and B must agree the nested `readings` shape before incident files are added.** The current `list[dict]` type is only a placeholder, in both Python and TypeScript. Each eventual reading should identify its value, unit, origin, sensor, and time as described in the handoff. Keep synthetic answer keys outside model input files.

The planned diagnosis shape is `cause_label`, `supporting_evidence`, `alternative`, `next_check`, and `uncertainty` (`low`, `medium`, `high`). A confirmation requires `diagnosis_id`, `incident_id`, `actual_cause`, `fix_performed`, `verifier`, and an ISO 8601 `timestamp`. `diagnosis_id` links the human outcome to the unchanged original prediction.

## Team handoff

- **Robotics cases and evaluation:** agree the reading schema and fault labels with the backend owner; add real team-authored incident files and separate held-out material.
- **Backend and integration:** implement provider diagnosis and durable request references, then save diagnoses to SQLite. Keep credentials on the server. Verify any task, feedback, and adapter workflow before exposing its status.
- **Frontend and integration:** connect the existing views to the diagnosis and confirmation routes when those routes become operational; add reading charts once the reading contract is fixed. Recharts is installed for that work.

The UI components under `frontend/src/components/ui` use the shadcn-style local component pattern and `frontend/components.json` is included for future additions. Tailwind CSS is configured. There is no sample chart because no measurement contract or readings exist yet.

## Repository layout

```text
backend/app/          FastAPI schemas, routes, incident loader, SQLite setup
data/incidents/       Empty; future versioned case files
data/evaluation/      Empty; future held-out cases and answer keys
frontend/src/api/     Typed browser API client
frontend/src/components/ui/  Local UI primitives
frontend/src/App.tsx  Three-view workspace
```

