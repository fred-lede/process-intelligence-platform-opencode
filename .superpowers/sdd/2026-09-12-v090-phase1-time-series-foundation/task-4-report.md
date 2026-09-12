# Task 4 Report — Phase 1 Time-Series UI

## Outcome

- Added a Standard Modeling / Time-Series Modeling selector without changing
  or removing any existing model type or downstream Model Center section.
- Added controls for the time column, 7/30/60/90-day comparison window, lag
  steps, rolling windows, and chronological holdout or walk-forward validation.
- Connected the UI to the stable `features/time_series/model` and
  `features/time_series/validation` operations through typed frontend APIs.
- Rendered localized time-axis and feature-quality warnings, the effective
  feature configuration, usable/dropped row counts, split row counts and date
  ranges, fold count, and leakage-check status.
- If feature preparation succeeds but strict chronological splitting fails,
  the UI preserves and displays the quality evidence instead of discarding it.
- Updated the Model Center guide and every new UI string in `zh-TW`, `en`, and
  `es-MX`.

## Files changed

- `src/features/model-center/ModelCenter.tsx`
- `src/lib/engine.ts`
- `src/components/guide/guideContent.ts`
- `src/i18n/zh-TW.json`
- `src/i18n/en.json`
- `src/i18n/es-MX.json`
- `.superpowers/sdd/2026-09-12-v090-phase1-time-series-foundation/task-4-report.md`

## Verification evidence

- `npm run build`
  - Exit 0; TypeScript compiled and Vite built 3,139 modules in 9.40 seconds.
- `engine/.venv/bin/pytest engine/tests/test_time_series_modeling.py -q`
  - Exit 0; `26 passed in 2.21s`.
- `node -e "...parse locale JSON and compare timeSeries keys..."`
  - Exit 0; all three locale files parsed and their time-series key sets match.
- `git diff --check`
  - Exit 0; no output.

The first focused-test attempt used the system `pytest` and did not start the
suite because that environment lacks the configured `pytest-cov` plugin. The
checked-in `engine/.venv` supplied the required plugin and produced the valid
test result above.

## Concerns

- The Phase 1 engine contract does not yet accept a date-window filter. The
  selected 7/30/60/90-day window is therefore recorded and shown as a requested
  comparison setting, with explicit UI and guide text that it is not yet an
  applied dataset filter.
- The current validation operation returns deterministic split indices, dates,
  row counts, and leakage evidence, but no fitted forecast. The UI therefore
  does not invent MAE, RMSE, R², or interval-coverage values; those remain for a
  later time-series estimator phase.
- This frontend has no configured unit/component test runner. UI verification
  in this task is TypeScript/Vite build-level plus focused engine contract tests;
  no interactive Tauri data-import run was performed.
- `docs/superpowers/plans/2026-09-12-v090-phase1-time-series-foundation.md`
  was already untracked and remains excluded from this task's commit.
