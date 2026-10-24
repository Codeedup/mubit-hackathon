# Robo Medic check-in evidence — 24 October 2026

## Revision and checks

- Fetched and fast-forwarded local `main` to `7a37b735629e5eb22e1c03b19ce2723cf7d2c619`, matching `origin/main` at check time. This revision already integrates the simulator, Mubit provider, API routes, browser flow and collection CLI.
- The improvements in this working tree are not yet on `origin/main`; use the current diff when preparing the judge build.
- Backend tests and frontend production build pass. The Vite build reports a chunk-size advisory.
- Offline captured payloads for API diagnosis and collection used the same Gemini endpoint, model, system instruction, role, and absence of tools/output-format overrides; only incident text differed. No answer key appeared in the collection user content.

## Verified browser flow

- In the simulator, injected a synthetic `n20_fl` jam. Captured incident `SIM-20261024T145611-07c8cdd4` contains target 150 RPM, observed 0 RPM, and about 1 A motor current. The injected fault is held in a separate local answer-key file, not in the incident sent to Mubit.
- On a clean backend at port 8002 and browser at port 5174, Mubit returned `wheel obstruction` through `gemini-3.8-flash`. The UI showed `readings[14].value` as source evidence, the saved verbatim reply, next check, request `mreq_01a16e6bc1237061858cb325aebe68bc`, and 5.15 s elapsed. The diagnosis is persisted in SQLite.
- Recorded the simulated technician outcome in local repair history. A second confirmation of the same diagnosis returned HTTP 409 and did not add another record. The prolonged stall later burned out the simulated motor. We reset the simulator, verified about 152 RPM at 0.047 A with no active faults, and amended the locally generated test outcome to describe that full recovery sequence accurately. This local amendment was not sent to Mubit.
- An older backend already on port 8000 handled the first browser attempt, returned an evidence error, and grouped that call into `Diagnose only 2`. It saved no diagnosis. The Vite proxy can now point at the intended backend via ignored `frontend/.env.local`; this machine uses `ROBO_MEDIC_API_PROXY_TARGET=http://127.0.0.1:8002`.

## Mubit console and collection gate

- The successful browser call appears in `robofix` under `Classify this robot fault`. Its traffic view shows 3 calls for the task, while the task summary still says 2 usable calls. The console shows 0 kept, 0 rejected, and 3 waiting for review; History's last reviewer pass says 2 new calls, 0 kept, 0 rejected. These counters update on different schedules.
- The new request's Request and Reply panels still say no text, although the backend received and saved the provider reply. The project warning still says this gateway serves `university-of-the-arts-london-1792787723691839484` while changes are written to `robofix`. Ask Mubit support to trace the request ID above and explain the blank panels, review queue, and warning.
- At about 16:06 Europe/London, a task-page refresh and retry failed: the console said the engine timed out after 10000 ms on `GET /v2/pathways`. The 3-call / 0-kept figures are the last readable state, not a fresh reviewer result.
- The 25-call ceiling has used 4 attempts: 2 earlier calls and 2 browser calls today. At most 21 remain. No collection CLI calls were sent because the review and visible-content gate has not cleared. `python -m backend.app.collect --other-attempts 2` previews the 40 prepared cases and remaining budget. When the gate clears, start with `--send --limit 1 --other-attempts 2`; inspect task grouping and reviewer state before any more calls.
- No adapter exists. No supported action for submitting a corrected label was found in the request/task UI or the checked guides. The request UI offers Good/Bad ratings without a corrected target. A local `POST /api/confirm` does not train Mubit. Do not attribute a later model answer to that local confirmation.
- The `robofix` Settings page currently shows 90 days for calls kept, and new versions after 25 examples. Mubit documents request/reply recording by default and adapter training from kept examples. Only synthetic incident data was sent. Separate privacy/ownership terms for any future physical data need confirmation from Mubit.

## Demo sequence (under 3 minutes)

1. **0:00–0:30:** Maintenance engineer, first triage job, and four possible labels. State that this is advisory and the case is synthetic.
2. **0:30–1:20:** Show the simulator jam and the captured target RPM, actual RPM, and current. The saved incident above is the repeatable example.
3. **1:20–2:05:** In the browser, show the saved Mubit diagnosis, source evidence, next safe check, model ID, raw reply, request reference, and elapsed time.
4. **2:05–2:35:** Open Feedback and show the locally recorded simulated outcome and repair history.
5. **2:35–3:00:** Open the Mubit task. Say 3 calls are visible in traffic, 0 kept, 0 rejected, review pending, and no adapter or verified correction. Do not claim measured time savings or improved accuracy.

If live provider latency threatens the slot, use a clearly labelled recording of this same verified flow. The saved diagnosis and repair history can also be shown without another Mubit call.
