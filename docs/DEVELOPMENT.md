# Development and checks

In your virtual environment, install backend development requirements:

```bash
python -m pip install -r backend/requirements-dev.txt
python -m unittest discover -s backend/tests -v
```

The focused suite checks evidence gating, immutable predictions, outcome
integrity, evaluation leakage, simulator intake, provider errors, imports,
request replay, local browser boundaries, and exact-call feedback matching.
Tests use temporary databases and mocked model calls; no credentials are needed.

## UI development

With offline mode configured in root `.env`, run the backend and Vite in separate terminals:

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
npm --prefix frontend run dev
```

Vite serves `http://localhost:5173` and proxies `/api` to port 8000. Override the
target using `ROBO_MEDIC_API_PROXY_TARGET` in ignored `frontend/.env.local`.
Use one backend and database per workspace. Rebuild before using `run.py`.

```bash
npm --prefix frontend run build
cd frontend
npx playwright install chromium
npm run test:e2e
```

Playwright starts a temporary offline workspace on port 8765. Desktop and phone
checks cover diagnosis, correction, persistence/reload, exact-run navigation,
export, uncertain cases, setup state, theme persistence, and horizontal overflow.
The operator's database is never used. Failure traces are in ignored `test-results/`.

## Evaluation

Diagnose cases first, then use **History & evaluation → Synthetic case evaluation**,
or run:

```bash
python -m backend.app.evaluate --split development --provider-kind local_fixture
python -m backend.app.evaluate --split held_out --provider-kind local_fixture
```

Scoring makes no new model calls. Each case uses its first stored prediction
across providers; reruns after correction cannot improve its score. Use separate
database snapshots for a prospective base/adapter comparison. Held-out answer
keys must not enter model input or feedback batches. Fixture scores check the
workflow, not AI performance.

## CI and recovery

GitHub Actions runs backend checks on Windows/Linux with Python 3.12/3.14, plus
a frontend build and desktop/mobile Playwright checks on Linux. Failures upload
browser traces. No repository secrets are required.

Export produces a portable evidence record, not a database restore. For full
backup, stop the app and copy SQLite, incidents, and any captured answer keys.
Restore to a separate directory and configure paths in `.env`. Preserve old
databases without provider traces separately; select a new `ROBO_MEDIC_DB_PATH`
instead of fabricating evidence or deleting operator history.
