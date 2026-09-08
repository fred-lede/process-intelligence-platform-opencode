# v0.6.0 Multilevel Data Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add optional hierarchical measurement metadata while preserving existing flat CSV workflows.

**Architecture:** Normalize optional metadata at import time, keep raw data immutable, and pass explicit filters and grain metadata through existing analysis APIs. Version-chain records retain the dataset schema and selected grain so reports and the assistant remain traceable.

**Tech Stack:** Python 3.12 with uv-managed pytest environment, pandas, React/TypeScript, Tauri 2.

**Spec:** `docs/superpowers/specs/2026-09-09-v060-multilevel-data-model-design.md`

## Global Constraints

- Existing CSV/Excel imports without metadata columns must continue to work unchanged.
- Raw source data is never overwritten.
- Analysis results must retain dataset ID, selected grain, and filters.
- No MES or cloud integration is introduced by this plan.

### Task 1: Metadata schema and import normalization

**Files:** Modify `engine/src/process_intelligence_engine/data/importer.py`, `engine/src/process_intelligence_engine/main.py`; test `engine/tests/test_importer.py`, `engine/tests/test_main_handlers.py`.

- [x] Add a canonical metadata-column map and return detected grain metadata with import results.
- [x] Preserve unknown columns and flat-import behavior.
- [x] Add tests for full metadata, partial metadata, and legacy CSV input.
- [ ] Run focused importer and handler tests; commit.

### Task 2: Filter and grain contract

**Files:** Create `engine/src/process_intelligence_engine/data/grain.py`; modify analysis handlers and `src/lib/engine.ts`; test `engine/tests/test_grain.py`.

- [x] Define `DataGrain` and `DataFilter` validation for supported fields.
- [x] Apply filters without mutating the registered dataset.
- [x] Reject unknown filter columns with a clear error.
- [x] Add typed frontend parameters and focused tests; commit.

### Task 3: SPC subgroup integration

**Files:** Modify `engine/src/process_intelligence_engine/main.py`, `src/features/spc/SPC.tsx`, `src/lib/assistantData.ts`; test SPC handler and frontend build.

- [x] Accept optional grain/filter parameters in `spc/analyze` and batch handlers.
- [x] Use `subgroup_id` or selected grouping field for X-bar-R/X-bar-S.
- [x] Include selected grain/filter and resulting sample counts in the assistant summary.
- [ ] Run SPC tests and frontend build; commit.

### Task 4: Persistence, reports, and assistant traceability

**Files:** Modify project manifest/version-chain metadata, report context, and assistant context builders; add regression tests.

- [x] Persist dataset schema metadata and active grain/filter with the dataset entity.
- [x] Include grain/filter in report metadata and assistant summaries.
- [x] Ensure project reopen restores metadata without changing raw data.
- [x] Run full engine suite and build; commit.

### Task 5: Documentation and release update

**Files:** Modify `README.md`, `docs/deployment.md`, locale strings if UI labels are added.

- [x] Document legacy flat mode and optional hierarchical fields.
- [x] Document examples for product, lot, machine, station, process step, and subgroup.
- [x] Update v0.6.0 release notes after all tests pass.
- [x] Run `git diff --check`, full pytest, frontend build, and `cargo check`; commit.
