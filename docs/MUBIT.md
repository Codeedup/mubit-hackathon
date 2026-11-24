# Mubit setup and integration

## Observation on 24 November 2026

The `robofix` task **Classify this robot fault** showed 31 kept examples,
**Waiting for more examples: 31 of 43**, and no adapter ready. Connect reported
no provider key. The October gateway/project warning remained. These are dated
observations, not live app configuration or an explanation of the threshold.

[Dated task evidence](evidence/mubit-task-status-2026-11-24.txt)

This release was verified offline with mocked HTTP contracts. No live inference
calls, management feedback submissions, training, or rollout were performed.

## Inference

For DeepSeek through OpenRouter, use the [OpenRouter route guide](OPENROUTER.md).
The instructions below describe the Gemini route.

1. Open your project in [Mubit console](https://app.mubit.ai/console/).
2. Add a Gemini API key under **Provider keys**, then create a project
   **inference** key under **Mubit keys**.
3. Copy `.env.example` to `.env`, choose `ROBO_MEDIC_PROVIDER=mubit`, and set
   `MUBIT_API_KEY`. Keep the console's Gemini base URL and a model your provider
   supports. The documented example is `gemini-3.8-flash`.
4. Restart. Diagnose one synthetic case and inspect its saved reply/model/request
   reference, then find the call in Requests.

The backend uses `/gemini/v1beta/models/{model}:generateContent` and the
`x-goog-api-key` header. Stable instructions/settings keep recurring calls in one
task. Answer keys, outcomes, and synthetic fault labels stay out of inference.
See the [official Gemini guide](https://docs.mubit.ai/guides/connect-gemini).

## Task status

Create a **project-scoped management key**, with `read` for status or `member`
for feedback, and configure:

```dotenv
MUBIT_MANAGEMENT_KEY=<management key>
MUBIT_MANAGEMENT_URL=https://api.mubit.ai
MUBIT_PROJECT_ID=<management API project ID>
MUBIT_TASK_ID=<classification task ID>
```

Use exact management API identifiers. Console workspace slugs may differ from
API project IDs. Select the task with the exact classifier instructions/model.
Restart, then use **Setup → Check Mubit status**. The backend reads
`GET /api/v1/tasks/{id}` and `/versions`, showing the check time, stage, dataset
rows, and returned versions. It does not assume a training threshold from row
counts. An inference configuration badge is not a provider health check.

## Reviewed feedback

1. Run a case through Mubit and save its inspected or simulated outcome.
2. Find the matching console request and copy its **call ID**. The gateway's
   `mreq_` reference may be a different identifier.
3. Reopen the exact diagnosis and use **Share the reviewed outcome**. Paste
   the call ID and select **Send outcome to Mubit**.
4. The backend verifies project, exact incident text, and raw reply. Blank or
   mismatched recordings stop submission.
5. It posts a rating and corrected label to
   `/api/v1/calls/{call_id}/feedback` with a stable idempotency key, then stores
   the returned feedback ID. Retrying a saved submission returns that receipt.

Ratings compare the original model label with the confirmed cause. Fixture runs
cannot be submitted, and free-text causes outside the four classifier labels
require review/mapping first. A console call cannot be linked to two diagnoses.
Saving an outcome locally makes no external call.

Ratings/corrections, kept examples, training, evaluation, and promotion are
separate stages. The app never starts training or promotes a model, and does not
assume every correction becomes an adapter target. See
[official tasks and ratings](https://docs.mubit.ai/train/tasks-and-ratings) and
[management calls API](https://docs.mubit.ai/reference/management-api/calls).

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing credentials | Root `.env`, inference key, provider mode, backend restart |
| Inference 403 | Provider key, provider access/quota, and project scope |
| Status unavailable | Management key/role, exact API project/task IDs, service availability |
| Feedback mismatch | Correct console call ID and full recorded input/reply |
| Unsupported reply | Exactly one accepted classifier label is required |
| Timeout | Retain the request reference; a new diagnosis is a deliberate new attempt |

Keep keys/databases out of Git. Start with synthetic cases and review Mubit data
settings before sending physical incident data. The historical collection CLI
is separate and is not an automatic training trigger.
