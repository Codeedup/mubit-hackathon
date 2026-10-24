# Mubit live collection gate — 24 October 2026

Project: `robofix` (`ws-bb11b91c689aa934`). Gemini base URL shown on its
Connect page: `https://api.mubit.ai/gemini`. Model: `gemini-3.8-flash`.
The backend key is server-side and was not copied into this note.

Two live synthetic `DEV-001` calls were made during this fix:

1. Official `google-genai` client, same fixed classification instruction and
   case text as the backend, no JSON response mode. HTTP succeeded and
   `response.text` was `unknown`.
2. Backend `POST /api/diagnose`, same classifier, returned HTTP 201. Mubit
   supplied `x-middleware-request-id:
   mreq_01a16e3c68e87841a6a705c3675fdd77`; the response text was
   `wheel obstruction`. The backend saved that diagnosis and its incident
   snapshot. The two outputs differed across calls; no claim of model
   improvement follows from them.

After a short processing delay, both calls appeared under `robofix` in the
new **“Classify this robot fault”** task. At 15:16 Europe/London it showed
**2 calls and 0 of 25 kept examples**, with status “Reviewing examples.”
Its History says **“Reviewer: 2 new calls, 0 kept, 0 rejected”** and
**“Sent for review: 2 new calls.”** The Examples kept tooltip says
**“0 rejected. The reviewer queued 2 calls today.”** The zero count is
currently a review queue, not evidence that either call was rejected.
Both `200 · answered` entries showed **“No message text in the request”**
and **“No text in the reply.”** An older “Classify this synthetic robot”
task showed **2 of 25 kept examples**, even though an inspected older request
panel was also blank. The blank panels alone therefore do not prove why the
new task has no kept examples.

The older task history shows the same review can take more than one pass:
one reviewer entry recorded **1 new call, 0 kept, 0 rejected**, followed
about 25 minutes later by **0 new calls, 1 kept, 0 rejected**. This supports
the interpretation that an initial zero-kept result can mean a call is
pending a later review pass. Mubit does not expose the per-call acceptance
reason in the task history.

The Tasks page also displayed this warning:

> This gateway serves university-of-the-arts-london-1792787723691839484.
> Changes here are written to robofix in the engine; a gateway started with
> MW_PROJECT=ws-bb11b91c689aa934 serves them.

The backend's `mreq_` header ID did not resolve as a console request page in
either project; the console rows have different internal UUIDs. The response
body did reach the backend, so a blank console panel does not mean the
provider returned an empty body. The gateway warning's relevance is unclear:
the calls are visibly grouped in `robofix`.

## Questions for Mubit support

1. Please trace the `mreq_` ID above and the two calls in the `robofix`
   task “Classify this robot fault.” Why do their console Request/Reply panels
   show no text? Are the two examples merely awaiting review, or is something
   preventing them from being kept? Is the gateway warning relevant despite
   the calls appearing under `robofix`?
2. What supported mechanism in this workspace accepts a technician-corrected
   label as an adapter training target? Please identify the exact API or console
   action and how to verify acceptance. A local `POST /api/confirm` does not
   submit that correction.

No collection batch was sent because visible Request/Reply and an advancing
kept-example count are required before spending the remaining call budget.
This testing used **2 of the user-authorized maximum 25 live Mubit calls**.

## Follow-up at 16:02 Europe/London

Two further synthetic browser calls were made, bringing the running budget to
**4 of 25 attempts**. The first was handled by a pre-existing older backend on
port 8000. Its frontend showed `Provider cited evidence absent from the
incident`, and its console row grouped under `Diagnose only 2` despite the
captured case being synthetic. No diagnosis was saved for that attempt. The
second used a clean backend from fetched `main` on port 8002. It returned and
saved `wheel obstruction` for `SIM-20261024T145611-07c8cdd4` through
`gemini-3.8-flash`, with header request ID
`mreq_01a16e6bc1237061858cb325aebe68bc`. This row grouped under the intended
`Classify this robot fault` task. The browser showed the raw reply and source
evidence, and local technician confirmation succeeded.

The intended task's traffic view now shows 3 calls, but its summary still says
2 usable calls. Details showed 3 waiting for review, 0 kept, and 0 rejected;
the latest History reviewer entry remains 2 new calls, 0 kept, 0 rejected.
The new console Request/Reply panels are blank even though the clean backend
saved the reply. The same gateway/project warning remains. The new request ID
above is the best trace for support. No collection CLI batch has been sent.

The request UI exposes Good/Bad ratings but no corrected-label target. The
checked documentation did not identify an action that accepts a technician
correction for adapter training. Please confirm whether such an action exists
and how its accepted target can be verified. The project currently displays
90 days for calls kept and first training after 25 examples; clarify retention
and training use before any physical incident data is sent.

At about 16:06 Europe/London, refreshing the intended task page showed
`The engine is not answering`; Details said `the engine timed out after 10000 ms
on GET /v2/pathways`. A retry showed the same failure. The last readable task
state is the 3-call traffic / 0-kept state above; a newer reviewer result could
not be verified while the engine was unavailable.
