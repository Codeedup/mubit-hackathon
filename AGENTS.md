# Project guidance

## Context and token efficiency

- Start by identifying the packages and files relevant to the task.
- Read only those files and their direct dependencies initially.
- Prefer targeted searches over repository-wide file dumps.
- Do not read entire logs when a short error excerpt is sufficient.
- Expand investigation only when required by evidence or dependencies.
- Do not repeatedly inspect unchanged files.

## Testing efficiency

- The project and hackathon sponsor favor a lean test suite. Add a test only
  when it protects a real failure mode, safety rule, data integrity boundary,
  or integration contract. Keep the smallest representative cases that do so.
- Do not add tests that merely repeat framework validation, pin fixture counts,
  duplicate another test, or check incidental implementation details. Remove
  redundant or obsolete tests as behavior changes.
- Avoid new test dependencies for low-risk changes. Prefer a targeted manual
  check when a one-off behavior does not justify permanent test code.
- During development, run tests for the affected package or component first.
- Run backend checks for API/provider changes and Playwright checks for user workflow changes.
- Run broader regression tests when changes cross package boundaries, affect shared interfaces, or introduce integration risks.
- Run all mandatory offline and safety validation gates before hardware testing or relevant integration milestones.
- Never skip safety-critical tests solely to save tokens.
- Summarize test results instead of returning large successful test logs.

## Scope

- Keep changes within the requested task and affected dependencies.
- Do not refactor unrelated packages without justification.
- Preserve immutable diagnosis snapshots, explicit source labels, and separate answer keys.
- Keep diagnoses advisory. Never add physical control commands or automatic training to this workflow.
- Do not make paid inference calls unless the user has authorized them and set a budget.

## Local workflow

- Read README.md and docs/ARCHITECTURE.md for the current product, not docs/archive/.
- Build with npm --prefix frontend run build; start with python run.py.
- Run python -m unittest discover -s backend/tests -v in the virtual environment.
- Browser checks: cd frontend and npm run test:e2e. They own a temporary workspace.
- Keep keys, SQLite files, runtime cases, node_modules, and generated builds out of Git.
