# Robo Medic

Local diagnostic workflow for the Mubit Night Shift project. The backend can
validate versioned incidents, save an immutable diagnosis and provider trace,
record a technician outcome, show repair history, and report
whether predictions matched inspected causes. Theo's simulator and browser UI
are integrated through these backend contracts. Live diagnosis can run through
Mubit's Gemini gateway when server-side credentials are configured.

## Run locally

Requires Node.js 22+ and Python 3.10+.

From the repository root, start the backend:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal, start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

To capture simulated faults, start the simulator in another terminal:

```powershell
python -m simulator.server --host 127.0.0.1 --port 8001
```

Its control dashboard is at `http://localhost:8001`. The backend polls its
telemetry and active faults, then writes validated version 1.0 incident files.
The simulator is optional; existing incident files and API routes work while it
is offline. Set `ROBO_MEDIC_SIMULATOR_URL` to change its local address.

Open `http://localhost:5173`; API docs are at `http://localhost:8000/docs`.
Vite proxies `/api` to port 8000. The default browser origin is
`http://localhost:5173`.

Copy `.env.example` to `.env` to configure the backend. `.env` and the local
SQLite database are ignored by Git. Keep credentials on the backend, never in
the frontend or browser.

### Mubit diagnosis

Set `ROBO_MEDIC_PROVIDER=mubit` and `MUBIT_API_KEY` in `.env`, then restart the
backend. The default model is `gemini-3.8-flash`. Set `MUBIT_MODEL` if your
workspace uses a different Gemini model, and set `MUBIT_BASE_URL` if the Mubit
console gives your workspace a different Gemini base URL. The default is
`https://api.mubit.ai/gemini`. For starter credit, choose a model listed in
your Mubit console. Add any provider key in the Mubit console, if your chosen
model is not covered by starter credit. The backend sends the incident JSON and stable task
instructions to Mubit, validates the structured result and evidence references,
and saves the model ID and Mubit request ID with the diagnosis. The browser
shows the returned diagnosis when the call completes and refreshes saved records
from the backend every 1.2 seconds. Mubit records request and answer content by
default, so use synthetic incidents unless your workspace is approved to send
physical incident data. See [Mubit's Gemini connection guide](https://docs.mubit.ai/guides/connect-gemini).

### Offline diagnosis fixture

`ROBO_MEDIC_PROVIDER=unavailable` is the default. Diagnosis requests return 503
in that mode. To exercise the complete API flow without keys, set
`ROBO_MEDIC_PROVIDER=local_fixture` in `.env` and restart the backend. This is a
deterministic rule-based fixture, not a model or Mubit request. Its records carry
`provider_kind=local_fixture`, `model_id=local-rule-fixture-v1`, and a
`local-fixture:` request reference. Task, training, and adapter status remain unavailable.

## Data contract and provenance

Each `data/incidents/*.json` file is one immutable version 1.0 incident with
`schema_version`, `id`, `robot_type`, `time_window`, `commanded_action`,
`readings`, `fault_codes`, `technician_note`, and `source_type`. Every reading
requires `sensor`, `value`, `unit`, `origin`, and a time with a timezone offset.
The loader rejects malformed files and duplicate IDs; it does not ask a model
to repair input. To revise a diagnosed case, create a new incident ID. Each
stored diagnosis includes a snapshot of the incident as it existed when run.

The 11 bundled cases are **synthetic**, including all their readings and notes.
Three are development examples; eight IDs beginning `HOLD-` are reserved for
held-out evaluation. Their answer keys are in
`data/evaluation/answer_keys.synthetic.json`, separate from incident files and
never supplied to the diagnosis provider. These are public synthetic fixture
keys, not private or physical inspection records. The incident files contain
observable readings and symptom notes, but no injected fault labels or
cause-specific fault codes. Do not tune task instructions
against held-out results before the baseline run.

Captured simulator incidents are also **synthetic**. Each reading uses the
backend's `sensor`, `value`, `unit`, `origin`, and timezone-aware `time`
fields. A metric is named in `sensor`, for example `n20_fl.rpm`; simulator
packet defaults and ground-truth fault labels are not presented as measured
readings or diagnosis evidence. Captured incidents have `source_type=synthetic`,
synthetic reading origins, and no fault code derived from the injected label.
Each injected label is stored separately in
`data/evaluation/captured/<incident_id>.json` (configurable with
`ROBO_MEDIC_CAPTURED_KEYS_DIR`). Those raw capture keys need an adjudicated cause
mapping before they can be scored with the synthetic evaluation command.

The diagnosis cause labels are `wheel obstruction`, `motor power/driver path`,
`encoder/reporting fault`, and `unknown`. Evidence uses `{field, explanation}`;
`field` must point to an existing top-level incident field, `fault_codes[n]`,
or a property of `readings[n]`. A diagnosis also requires an alternative, next
check, and low/medium/high uncertainty. The stable task instructions and
provider boundary are in `backend/app/provider.py`.

## API flow

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/api/incidents`, `/api/incidents/{id}` | Validated incident files |
| `POST` | `/api/diagnose` | Diagnose by incident ID; save incident snapshot, structured result, raw response, model ID, and request reference |
| `GET` | `/api/diagnoses`, `/api/diagnoses/{id}` | Retrieve saved predictions; list can filter by `incident_id` |
| `POST` | `/api/confirm` | Save one technician-confirmed outcome per diagnosis without changing the prediction |
| `GET` | `/api/repairs` | Repair history with cause, fix, inspection note, verification kind, and prediction match; can filter by `incident_id` |
| `GET` | `/api/evaluation/confirmed` | Accuracy against inspected physical outcomes, grouped by provider and model |
| `GET` | `/api/metrics` | Local counts, simulator intake, and configured diagnosis provider status |

Example diagnosis request:

```json
{"incident_id":"DEV-001"}
```

Use the returned diagnosis `id` to record a synthetic simulation outcome:

```json
{
  "diagnosis_id": "<returned diagnosis id>",
  "incident_id": "DEV-001",
  "actual_cause": "wheel obstruction",
  "fix_performed": "Cleared the simulated blockage and checked wheel rotation.",
  "inspection_note": "Simulator state showed a wheel jam and recovery after clearing it.",
  "verifier": "simulator operator",
  "timestamp": "2026-10-24T12:00:00Z"
}
```

The confirmation route requires an existing diagnosis with the same incident
ID, a verifier, an inspection note, and a timezone-aware timestamp. It rejects
duplicate confirmations for the same diagnosis. Repair history remains available
even if a later edit removes the incident file, because the original diagnosis
keeps its incident snapshot. `actual_cause` can name a cause outside the three
prediction labels when inspection discovers one; an exact-match score then
counts that prediction as a mismatch. The application does not execute repair
actions. Confirmations for synthetic incidents are saved as
`verification_kind=synthetic_simulation`; confirmations for physical incidents
are saved as `verification_kind=inspection`.

Provider unavailable, timeout, malformed response, and nonexistent evidence
references return explicit errors. Invalid provider results are not saved.

## Evaluation

`GET /api/evaluation/confirmed` compares predictions with inspected technician
outcomes from physical incidents. Synthetic simulations remain in repair history
but are excluded from this report. It groups by provider kind and model ID. Within a group, the most
recent confirmed diagnosis for each incident contributes one case to accuracy;
`confirmed_diagnosis_count` also reports all confirmed runs. An empty group has
no accuracy value. This is diagnostic accuracy against verified causes.

Technician confirmations remain local repair history. They are ground truth for
the inspected-case evaluation above; saving one does not submit a correction
or start Mubit training. Task and adapter progress can be viewed in the Mubit
console; this app does not read those statuses.

Synthetic answer-key evaluation is a separate offline command. It scores the
first stored diagnosis for each case across providers, before any later saved
correction can influence a rerun. A case whose first diagnosis belongs to a
different provider is reported missing for the requested provider.
Previously saved synthetic diagnoses whose incident snapshots contain fault
codes are excluded from this score, since older simulator captures and fixtures
could encode the injected answer there. Run it with:

```powershell
python -m backend.app.evaluate --split development --provider-kind local_fixture
python -m backend.app.evaluate --split held_out --provider-kind local_fixture
```

The output includes the key count, evaluated count, missing and excluded case
IDs, exact matches, and per-case predictions. Missing predictions are not silently counted
as successes. Keep development and held-out results separate. Neither of these
accuracy measures is Mubit’s adapter-to-provider agreement test; no adapter
result is available yet.

## Checks and current limits

Backend tests use a temporary database and incident directory:

```powershell
pip install -r backend/requirements-dev.txt
python -m unittest discover -s backend/tests -v
```

The frontend supports diagnosis, technician outcome logging, repair history,
and inspected-case evaluation. The local fixture is for software flow checks;
its predictions are not evidence of model performance. There is no Mubit
correction submission or adapter management in this app. The API currently has
no authentication and is intended for local use. Repair history is stored
locally in SQLite and is not adapter learning.
