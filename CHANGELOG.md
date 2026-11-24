# Changelog

## Unreleased — DeepSeek / OpenRouter

- Added OpenAI-compatible label classification directly through OpenRouter or through Mubit's OpenRouter route.
- Defaulted the OpenRouter route to DeepSeek V4.1 Flash 1017, with reasoning disabled and a 128-token response limit.
- Kept direct OpenRouter records separate from Mubit inference, feedback, and evaluation.
- Added connection instructions and mocked HTTP contract checks. Live verification is recorded separately after account setup.

## 1.0.0 — 24 November 2026

- Completed the responsive diagnostics workspace, search/filter, theme choice,
  setup guide, and exact-run history.
- Added fresh synthetic cases, immutable JSON import, workspace export, and UI evaluation.
- Added one launcher for the built UI, API, and optional simulator, with port
  checks, loopback binding, and simulator shutdown.
- Added diagnosis replay protection and local browser write boundaries.
- Added optional Mubit task/version reads and explicit correction submission,
  with exact input/reply matching and durable acknowledgements.
- Added backend boundary checks, desktop/mobile Playwright coverage, and CI.
- Updated Mubit evidence, archived October planning, and removed generated
  metadata, unused UI dependencies, and vendored skill caches.

Live Mubit operations remain account-dependent and were not run for this release.
No adapter performance improvement is claimed.
