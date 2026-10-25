# Robo Medic: archived skeleton decision checklist

> Historical planning document from before the working backend and frontend.
> Its statements that diagnosis always returns 503, that data directories are
> empty, and that there are no tests describe an older revision. See
> [README.md](README.md) for the submission behavior.

This is a decision checklist for the team, based on the code in this repository. **Open** means the behavior has not been agreed or implemented; a suggested default is a proposal, not a description of the current system. Resolve the decisions in dependency order before treating the workspace as a working diagnostic tool.

## What the skeleton actually does

```text
Team-authored JSON in data/incidents/
    -> validated by Incident -> GET /api/incidents and /api/incidents/{id}
    -> shown in the Diagnostics view
    -> POST /api/diagnose currently returns 503
    -> no diagnosis is written by any route
    -> POST /api/confirm can save a confirmation only for an existing diagnosis
    -> GET /api/metrics counts local rows and reports provider/task/adapter unavailable
```

The three SQLite tables (`diagnoses`, `confirmations`, `evaluations`) are created empty. Both data directories contain only `.gitkeep`. The frontend fetches incident lists and metrics; its diagnosis button is disabled, feedback is an empty state, and readings are shown only as a count. There are no tests in the repository. These are implementation facts, not pending design choices.

## Decisions to record

For each item, write the chosen rule, owner, and acceptance example in the decision record at the end. A choice is complete when both API and UI behavior, where relevant, are clear enough to implement and test.

### 1. Incident intake and source of truth — Open

- **Decide:** Who creates incident files, what makes a case ready for diagnosis, whether cases may be edited after a diagnosis, and how versions are named. Define required evidence and whether incomplete cases are rejected or flagged.
- **Existing skeleton:** `data/incidents/*.json` is loaded on every request. Invalid JSON/schema or duplicate IDs fail the whole incident list with HTTP 500. No upload or editing workflow exists.
- **Suggested default:** Treat files as reviewed, immutable snapshots; use a new ID or explicit revision for a correction. Keep a provenance record for each reading.
- **Touches:** `backend/app/incidents.py`, `backend/app/schemas.py`, `data/incidents/`, Diagnostics view.

### 2. Reading contract and display — Open; blocks real cases and charts

- **Decide:** Exact reading fields and types: sensor name, numeric or categorical value, unit, timestamp and timezone, origin/source, quality or missing-value flag, and ordering. Decide whether readings represent a time series or isolated observations and what charts are meaningful.
- **Existing skeleton:** Python accepts `list[dict[str, Any]]`; TypeScript uses `Record<string, unknown>[]`. The UI displays the count only. The README explicitly assigns the contract to owners A and B.
- **Suggested default:** Define one versioned `Reading` schema shared in meaning by API and browser, with explicit timestamps and units; reject values that cannot be interpreted.
- **Touches:** `backend/app/schemas.py`, `frontend/src/api/client.ts`, `frontend/src/App.tsx`, incident files.

### 3. Fault labels and ground truth — Open

- **Decide:** Allowed `cause_label` and `actual_cause` values; whether multiple causes are possible; how unknown, ambiguous, and no-fault outcomes are represented; who adjudicates conflicting technician reports. Decide which fault codes are raw robot codes versus normalized labels.
- **Existing skeleton:** These fields are free text. No taxonomy or answer keys are present.
- **Suggested default:** Maintain a documented label set with an `unknown` route and keep evaluation answer keys outside incident input files.
- **Touches:** `backend/app/schemas.py`, `data/evaluation/`, confirmation and evaluation workflows.

### 4. Diagnosis request and provider lifecycle — Open; blocks the main action

- **Decide:** Which provider/model or task is used, what incident evidence is sent, whether a request is synchronous or queued, timeout/retry/cancel behavior, and what status and durable request reference are exposed. Define behavior when provider credentials or service are unavailable.
- **Existing skeleton:** `POST /api/diagnose` accepts an incident ID and always returns 503. `DiagnosisRecord` has optional `request_reference` and `model_id`, but no route creates it. Metrics hard-code `provider_status=not_configured`, `task_status=unavailable`, and `adapter_status=unavailable`.
- **Suggested default:** Validate the incident first; send a server-side request; save the provider reference and immutable result; expose a status/read path if requests can outlive one HTTP call. Keep credentials on the server.
- **Touches:** `backend/app/main.py`, `backend/app/settings.py`, `backend/app/db.py`, `backend/app/schemas.py`, `.env.example`, browser API client.

### 5. Diagnostic output and human safety gate — Open

- **Decide:** Whether the existing fields (`cause_label`, `supporting_evidence`, `alternative`, `next_check`, `uncertainty`) are sufficient; how evidence cites specific readings; what to do with invalid, contradictory, or low-confidence output; who may approve a next check. Define whether the system may only advise or may ever trigger robot actions.
- **Existing skeleton:** `Diagnosis` validates field presence and the three uncertainty levels, but has no evidence references or decision threshold. No robot-control interface exists.
- **Suggested default:** Keep results advisory, preserve the raw evidence used, show uncertainty and alternative prominently, and require an operator for any physical check. No live flight commands without explicit operator authorization.
- **Touches:** `backend/app/schemas.py`, provider integration, Diagnostics view, tests.

### 6. Diagnosis persistence, repeat runs, and retrieval — Open

- **Decide:** Whether one incident can have many diagnoses, how reruns are distinguished, how duplicate clicks and provider retries are made idempotent, and which diagnosis a technician confirms. Define routes to retrieve diagnosis history and error cases for partial provider success.
- **Existing skeleton:** SQLite has a `diagnoses` table and `DiagnosisRecord`, but no writer or reader route. `POST /api/confirm` expects a stored diagnosis ID, so the end-to-end path cannot currently complete.
- **Suggested default:** Store each completed run with a unique ID, incident version, timestamps, model ID, and request reference; expose it through a read route; never overwrite a prior prediction.
- **Touches:** `backend/app/db.py`, `backend/app/main.py`, `backend/app/schemas.py`, `frontend/src/api/client.ts`.

### 7. Technician confirmation and correction — Open

- **Decide:** Who can verify, whether a confirmation may be revised or retracted, how the fix is validated, and which timestamp is authoritative. Decide how to handle a diagnosis tied to a case whose file has since changed.
- **Existing skeleton:** `POST /api/confirm` requires diagnosis and incident IDs, cause, fix, verifier, and timestamp. It rejects missing/mismatched IDs and permits only one confirmation per diagnosis. There is no listing, edit, audit, or UI form.
- **Suggested default:** Make confirmations attributable and auditable; represent a correction as a new revision rather than silently changing the verified outcome.
- **Touches:** `backend/app/main.py`, `backend/app/db.py`, `frontend/src/App.tsx`.

### 8. Evaluation design and release criteria — Open

- **Decide:** How held-out cases are selected, split and protected from model input or feedback, who owns answer keys, what metrics matter (for example top cause accuracy, uncertainty calibration, evidence quality, and unsafe next-check rate), and the threshold for a demo or release.
- **Existing skeleton:** `data/evaluation/` is empty and `evaluations` has only a generic `result_json` field. The UI shows local counts, not model performance.
- **Suggested default:** Freeze a small held-out set and rubric before tuning; report sample size and per-label results alongside aggregate metrics.
- **Touches:** `data/evaluation/`, evaluation runner to be created, `backend/app/db.py`, Intelligence view.

### 9. Feedback, tasks, and adapter improvement loop — Open

- **Decide:** Whether confirmed outcomes are sent to a provider, which records qualify, review/redaction requirements, task or adapter creation steps, versioning, evaluation before promotion, rollback, and how status is displayed. Define whether feedback is manual, batched, or automatic.
- **Existing skeleton:** Confirmation is stored locally only. No provider feedback, task, or adapter workflow exists; status fields are hard-coded unavailable.
- **Suggested default:** Require an explicit reviewed batch, keep training and held-out material separate, and promote a new adapter only after the agreed evaluation gate.
- **Touches:** provider integration, `backend/app/db.py`, `backend/app/schemas.py`, Intelligence view.

### 10. User workflow and state handling — Open

- **Decide:** Who can run a diagnosis or confirm an outcome; what each view shows while a request is pending, failed, retried, or completed; whether selected incident and diagnosis persist across navigation; and when counts refresh.
- **Existing skeleton:** The Diagnostics button is disabled. Feedback has no form or diagnosis list. The browser client only implements `GET /api/incidents` and `GET /api/metrics`.
- **Suggested default:** Implement a visible `select -> diagnose -> review -> confirm` path with explicit loading and error states, and show the stored diagnosis ID before confirmation.
- **Touches:** `frontend/src/App.tsx`, `frontend/src/api/client.ts`, backend routes.

### 11. Local operations, access, and data handling — Open

- **Decide:** Whether the prototype is strictly single-user/local or shared; authentication and verifier identity for shared use; retention and backup of SQLite and incident data; what incident content can leave the machine; secret storage; and recovery after database or provider failure.
- **Existing skeleton:** Local SQLite, one configured CORS origin, no authentication, no provider credentials, and no migration or backup procedure.
- **Suggested default:** Document local-only use until access control and data-handling rules are agreed. Do not place provider credentials in browser code or incident files.
- **Touches:** `backend/app/settings.py`, `.env.example`, deployment setup, API routes.

### 12. Validation gates — Open

- **Decide:** Required checks for incident fixtures, API contracts, provider failures, diagnosis parsing, confirmation integrity, evaluation leakage, and UI flow. Define the offline and safety checks required before any robot or hardware integration.
- **Existing skeleton:** No test files or CI configuration are tracked. The README documents manual local startup only.
- **Suggested default:** Start with schema and route tests using temporary case files and SQLite, then add provider mocks and end-to-end UI coverage. Run the mandatory offline and safety gates before hardware testing; never issue live flight commands without explicit operator authorization.
- **Touches:** new tests and CI configuration; affected backend and frontend modules.

## Suggested decision order

1. Agree incident versioning, reading schema, and fault labels (1–3).
2. Agree diagnosis lifecycle, output safety, and persistence (4–6).
3. Agree technician confirmation and the browser path (7 and 10).
4. Freeze evaluation criteria before any feedback or adapter promotion (8–9).
5. Record operating rules and validation gates before integration or hardware work (11–12).

## Decision record template

Copy one block per item into a team decision log:

```md
### Decision <number>: <name>
Status: proposed | agreed | implemented | verified
Owner: <person/team>
Choice: <precise rule, including failure behavior>
Reason: <why this choice>
API/data/UI impact: <contracts and files>
Acceptance example: <input, expected result, and error case>
Date: <YYYY-MM-DD>
```
