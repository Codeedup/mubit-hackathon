# Contributing

Read [architecture](docs/ARCHITECTURE.md) and [development](docs/DEVELOPMENT.md).
Keep changes focused and add only checks that protect real behavior or boundaries.
Backend and browser checks must pass before merging.

Keep synthetic and physical evidence distinct. Preserve prediction snapshots,
human verification, and separate evaluation answer keys. Do not add live control
commands to the diagnosis path or silently replace failed inference with a fixture.

Never commit credentials, local databases, runtime captures, or generated builds.
Document external side effects. Prompt, model, or format changes can create a
new Mubit task; check that impact before comparing with older results.
