# Robo Medic: two-minute software demo

This script uses the current synthetic simulator and local diagnosis workflow.
It requires one backend at the address used by Vite's `/api` proxy. Check
`http://localhost:5173/api/metrics` before starting. Follow the startup steps
in the [README](../README.md). Select `ROBO_MEDIC_PROVIDER=local_fixture` for
the repeatable offline route; announce that choice before any diagnosis.

## Live route

| Time | Show and say |
| --- | --- |
| 0–20 s | Open the bench. "Repeated robot faults cost technician time. These cases are synthetic, from a four-motor simulator or bundled examples." Point to the source label. |
| 20–50 s | In the simulator, inject a motor fault, then open the new `SIM-*` case. Point to commanded RPM, reported RPM/current, timestamps, and `synthetic` origins. If capture has not arrived, open a bundled `DEV-*` case. |
| 50–85 s | Diagnose with the **offline rule fixture**. Say it is deterministic and is not a Mubit or LLM answer. Show the evidence link, uncertainty, next check, raw fixture result, and `local-fixture:` reference. The app never acts on the recommendation. |
| 85–105 s | Record a simulated outcome after checking the simulator state, then show it in history and the Learning Loop. This stays in local SQLite; it does not train Mubit. |
| 105–120 s | Explain the earlier Mubit route using the documented `mreq_01a16e6bc1237061858cb325aebe68bc` synthetic request. "The team reports Mubit could not produce an adapter during the event because its servers were overloaded. We cannot show adapter improvement." |

## Saved-result route

If the **original local SQLite database** containing the 24 October Mubit run
is available, start the backend with `ROBO_MEDIC_DB_PATH` pointing to it and
the matching incident directory. Verify `/api/diagnoses` contains the exact
request ID above before the demo. Open that saved diagnosis in the browser and
show its raw label, model, evidence, and local outcome. No fresh Mubit call is
needed. The database is ignored by Git, so a fresh clone cannot show this
record unless the team supplies its own saved data.

If the database is absent, use the live offline route and show the
[dated check-in record](../CHECKIN_EVIDENCE_2026-10-24.md) as **historical
evidence**, rather than presenting a fixture result as a saved Mubit result.
Do not quote a current Mubit kept count: the app has no console connection.

## Rehearsal checklist

1. Confirm exactly one backend, one proxy target, and the expected
   `provider_status` in `/api/metrics`. That field describes configuration.
2. Confirm simulator capture or the chosen bundled incident is visible.
3. Run one fixture diagnosis and record a simulated outcome. Reload the page
   to confirm both persist in the selected SQLite database.
4. Practice the saved-result or historical-evidence fallback and state clearly
   which path the audience saw.
