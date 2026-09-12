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

## Review fixes

### Changes

- Replaced the tautological time-column self-check with the validation API's
  supported `not_checked` result when no real feature-source timestamp columns
  are available.
- Added backend `window_days` support to both time-series operations. The engine
  now selects the trailing wall-clock interval relative to the latest timestamp,
  so 7-day and 90-day requests operate on different data.
- Added applied UTC window bounds plus target and input snapshots to the feature
  configuration.
- Added source-order UTC-normalized timestamps to the validation response. Split
  labels format these values in the effective modeling timezone and include the
  time of day for hourly and minute-level data.
- Made time-series target options independent of the hidden standard model type.
  Target, inputs, window, lag, rolling-window, strategy, time-column, mode, and
  dataset changes invalidate both displayed results and in-flight responses.
- Localized `daily`, `hourly`, `minute`, `coarse`, and `unknown` frequency values
  in all three supported locales.
- Added an explicit localized state explaining that MAE, RMSE, R², and interval
  coverage are unavailable until a time-series estimator is fitted.

### TDD and verification evidence

- RED: the two new focused window/API tests failed with `2 failed, 26 deselected`:
  a 7-day request still returned all 100 rows, and validation configuration had
  no `window_days` field.
- Focused GREEN: window/API plus legacy default tests passed
  `4 passed, 24 deselected in 2.13s`.
- Full focused file: `engine/.venv/bin/pytest
  engine/tests/test_time_series_modeling.py -q` passed `28 passed in 2.27s`.

### Remaining concerns

- Forecast metrics remain intentionally unavailable because Phase 1 does not fit
  a time-series estimator. The UI now says this directly instead of presenting
  split evidence as forecast performance.
- The frontend still has no configured unit/component test runner. Async stale
  result protection is compile-checked but was not exercised by a component test.
- The initial concerns about unapplied day windows and an implicit metrics gap are
  superseded by this review-fix section.

## Takeover fix pass

### Changes

- Updated the model and validation handlers so time-series quality metadata and
  frequency defaults are computed from the selected trailing window when
  `window_days` is supplied. This keeps warnings, frequency, row counts, split
  labels, and generated features aligned to the same engine input.
- Added a focused regression test proving duplicate timestamps outside the
  selected window no longer affect the returned quality summary.

### Verification evidence

- `engine/.venv/bin/pytest engine/tests/test_time_series_modeling.py -q`
  - Exit 0; `29 passed in 2.44s`.
- `npm run build`
  - Exit 0; TypeScript compiled and Vite built 3,139 modules in 10.19 seconds.
- `git diff --check`
  - Exit 0; no output.

### Remaining concerns

- The stale in-flight response protection remains build-verified only; no
  frontend unit/component test runner is configured in this repository.
- CodeGraph is not initialized for this checkout, so structural inspection used
  local file reads instead.
