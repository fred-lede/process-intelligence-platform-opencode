# TASK.md

## Completed
- Task 2 (DOE Design Library): Added CCD + Box-Behnken design generators to
  `engine/src/process_intelligence_engine/modeling/doe.py`, plus shared
  `_build_runs` helper (refactored full/fractional factorial to use it).
  Tests: 10 passed in test_doe.py; full suite 103 passed.
  Commit: eb7c247
- Task 4 (DOE IPC + Frontend Wrapper): Added `modeling/doe/generate` IPC handler
  in `main.py` with `_handle_doe_generate` dispatcher. Added `generateDOEDesign`
  frontend API wrapper with `DOEFactor`/`DOEDesignResult` types in `engine.ts`.
  Tests: 4 passed in test_main_doe.py; full suite 111 passed. tsc clean.
  Commit: pending

## In Progress
- None

## Pending
- Next DOE tasks (TDD) as specified in plan.
