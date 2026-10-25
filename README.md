# Robo Medic

Robo Medic is a local technician workflow for **synthetic robot faults**. The
four-motor simulator supplies telemetry. The backend validates an incident,
asks the configured classifier for one fault label, builds an advisory from
the readings, and stores the result. A technician can record a simulated
outcome locally without changing the original prediction.

```text
Simulator or bundled synthetic case
  -> validated data/incidents/*.json
  -> Mubit one-label inference OR explicit offline rule fixture
  -> application evidence, uncertainty, and next check
  -> local outcome and evaluation
```

The diagnosis is advice only. It issues no simulator control command. This
submission does not include a physical-board intake.

## Submission status

| Status | What can be shown |
| --- | --- |
| Implemented | Version 1.0 incidents, simulator capture, diagnosis persistence and provenance, technician outcomes, local evaluation, and the bench/ledger UI. |
| Demonstrated earlier | A synthetic `SIM-*` jam received `wheel obstruction` through Mubit on 24 October 2026, request `mreq_01a16e6bc1237061858cb325aebe68bc`, model `gemini-3.8-flash`. The reply and outcome were saved in a local SQLite database; that database is not part of a fresh clone. See [the check-in record](CHECKIN_EVIDENCE_2026-10-24.md). |
| Demonstrable offline | The same API and UI workflow runs with `ROBO_MEDIC_PROVIDER=local_fixture`. This deterministic rule fixture is neither Mubit nor an LLM. |
| Unavailable | No adapter was produced and no adapter improvement was measured. The team reports that Mubit staff said overloaded servers prevented adaptation during the event; no written staff statement or exact communication time is in this repository. The last documented console check on 24 October showed zero kept examples for the intended task, not a current count. |
| Planned, outside this submission | Adapter comparison if Mubit makes one available. Local confirmations are not sent as training feedback. |

A saved Mubit `mreq_` ID proves a routed inference response reached the backend.
It does not prove that the console retained its request/reply text, kept an
example, or trained an adapter. `/api/metrics.provider_status=mubit` means the
provider is **configured**; it is not a health check.

## Run locally

Requires Python 3.10+ and Node.js 22+. Run commands from the repository root
unless a step changes directory. The default provider is `unavailable`, so
choose a mode explicitly in `.env`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
Copy-Item .env.example .env
```

For the repeatable offline demo, set `ROBO_MEDIC_PROVIDER=local_fixture` in
`.env`. Start the API:

```powershell
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, start the frontend:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to `127.0.0.1:8000` by
default. Check `http://localhost:5173/api/metrics` before the demo to ensure
the browser reaches the intended backend and incident directory. If port 8000
is already used, set `ROBO_MEDIC_API_PROXY_TARGET=http://127.0.0.1:<port>` in
ignored `frontend/.env.local` and start the API on the same port. Use one
backend process and one SQLite path. `ROBO_MEDIC_DB_PATH` and
`ROBO_MEDIC_INCIDENT_DIR` can be set in `.env`; relative paths resolve from the
repository root.

The bundled `DEV-*` and `HOLD-*` incidents are synthetic and work with the
simulator off. For a new synthetic capture, start the optional simulator in a
third terminal:

```powershell
python -m simulator.server --host 127.0.0.1 --port 8001
```

Open `http://localhost:8001`, inject a fault, and watch for a `SIM-*` case in
the bench queue. The simulator uses four virtual motors; its readings are
labelled `synthetic`. Injected fault labels are stored separately from the
incident input. The simulator is optional for inspecting stored cases.

### Provider modes

| `.env` value | Behavior |
| --- | --- |
| `ROBO_MEDIC_PROVIDER=local_fixture` | Explicit offline rule fixture. Records use `provider_kind=local_fixture`, a `local-fixture:` reference, and a fixture model ID. |
| `ROBO_MEDIC_PROVIDER=mubit` | Live Mubit inference using server-side `MUBIT_API_KEY`, `MUBIT_MODEL`, and `MUBIT_BASE_URL`. Only use after a separate live rehearsal; gateway availability is not established by this submission. |
| `ROBO_MEDIC_PROVIDER=unavailable` | Diagnosis returns 503; stored incidents, diagnoses, and outcomes remain readable. |

The Mubit provider in [provider.py](backend/app/provider.py) sends fixed
instructions and a label-free incident description, then accepts exactly one
of `wheel obstruction`, `motor power/driver path`, `encoder/reporting fault`,
or `unknown`. Application rules select evidence and a next check; an
unsupported model label is downgraded to `unknown` while its raw reply remains
stored. Timeouts and provider errors appear on screen and do not silently
switch to the fixture. Keep `.env`, keys, local SQLite, and logs out of Git.

## Data and evaluation

Every incident has an ID, source label, time window, action, note, fault codes,
and readings with sensor, value, unit, origin, and timezone-aware timestamp.
The loader rejects malformed files and duplicate IDs. Diagnoses store an
immutable incident snapshot, provider kind, model ID, raw reply, request ID,
and advisory. `POST /api/confirm` stores one outcome per diagnosis without
editing that prediction. The API is local-only and has no authentication.

The browser's Learning Loop counts **saved local** Mubit diagnoses and
outcomes. It cannot query Mubit's kept-example count. The checked-in
`backend.app.collect` tool and its attempt-before-send ledger remain available
as historical work, but the prepared 40 cases are not part of this demo and
must not be sent while adaptation is unavailable.

To inspect stored results, open `/api/diagnoses`, `/api/repairs`, and
`/api/evaluation/confirmed`. Synthetic answer-key evaluation is separate:

```powershell
python -m backend.app.evaluate --split development --provider-kind local_fixture
python -m backend.app.evaluate --split held_out --provider-kind local_fixture
```

This reports exact matches only for stored first predictions and lists missing
cases; it does not measure adapter improvement. The fixture result is a
workflow check, not model performance evidence.

## Demo and checks

Follow [the two-minute demo script](docs/DEMO.md). The
[24 October Mubit support handoff](MUBIT_SUPPORT_HANDOFF_2026-10-24.md)
documents the prior gateway and console observations. The older
`PROCESS_DECISIONS.md` is an archived skeleton checklist, not current behavior.

```powershell
pip install -r backend/requirements-dev.txt
python -m unittest discover -s backend/tests -v
cd frontend
npm ci
npm run build
```
