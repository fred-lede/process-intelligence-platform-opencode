# Three-Level Categorical Factorial DOE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a three-level categorical-factor DOE model that can reproduce the supplied Minitab analysis for `output-volume-CPK`, including main effects, all two-factor interactions, ANOVA, Pareto, main-effects, interaction, and residual plots.

**Architecture:** Keep the existing continuous `doe_linear` and `doe_quadratic` models unchanged. Add a separate `doe_categorical_factorial` model path that uses explicit effect/dummy coding for each selected categorical factor, includes all main effects and two-factor interactions, excludes the three-factor interaction by default, and exposes its term metadata so statistical output and charts use the same design matrix.

**Tech Stack:** Python, pandas, NumPy, scikit-learn, SciPy, pytest, React/TypeScript, Plotly.

**Spec:** `docs/superpowers/specs/2026-09-05-v030-complete-spec.md` (existing project specification; this plan extends the model catalog with the requested Minitab-compatible factorial mode).

## Global Constraints

- Preserve existing `doe_linear` and `doe_quadratic` behavior and serialized model compatibility.
- Treat selected factor levels as categorical labels, even when their values are numeric.
- The default model includes three main effects and all three two-factor interactions, but not the three-factor interaction.
- The implementation must preserve original factor labels and level order for prediction, reporting, and audit metadata.
- A model must reject unseen levels at prediction time with a clear validation error; it must not silently extrapolate a category.
- Do not claim equivalence to Minitab unless the target, factor levels, model terms, degrees of freedom, and data rows match.

## Review Focus

- Numeric-looking levels (`40/60/80`, `5/7/9`, `0/0.5/1`) must remain categorical rather than continuous; test this in the design-matrix contract.
- The 27-row full 3×3×3 design must produce 18 model degrees of freedom and 8 residual degrees of freedom; test the exact structure.
- Missing combinations or duplicated combinations must be surfaced in readiness/fit diagnostics rather than hidden; test both conditions.
- Prediction with an unseen level must fail with a named validation error; test the error contract.
- Existing continuous DOE models and old persisted models must remain unchanged; run regression tests for both paths.

### Task 1: Define the categorical factorial design-matrix contract

**Files:**
- Create: `engine/src/process_intelligence_engine/modeling/categorical_doe.py`
- Test: `engine/tests/test_categorical_doe.py`

**Interfaces:**
- Produces `build_categorical_factorial_matrix(df: pd.DataFrame, factors: list[str], include_two_factor_interactions: bool = True, include_three_factor_interaction: bool = False) -> CategoricalDesignMatrix`.
- `CategoricalDesignMatrix` contains the numeric matrix, ordered term names, factor level metadata, term-to-factor metadata, and residual/model degrees of freedom.
- Produces `validate_categorical_factorial_design(df: pd.DataFrame, factors: list[str]) -> dict` with level counts, duplicate/missing-combination diagnostics, and a stable status.

- [ ] **Step 1: Write failing tests** for three numeric-looking three-level factors, exact level order, effect/dummy-coded columns, term names, and the 18-df full two-factor design.
- [ ] **Step 2: Run** `pytest engine/tests/test_categorical_doe.py -q` and confirm the new API/design tests fail.
- [ ] **Step 3: Implement** the matrix builder using an explicit reference-level coding convention documented in metadata; generate 2 columns per factor and 4 columns per two-factor interaction, with an intercept handled consistently.
- [ ] **Step 4: Implement** design validation for duplicate runs, missing Cartesian combinations, fewer than two levels, and unsupported null values.
- [ ] **Step 5: Run** the focused tests and verify the supplied 27-row design yields 18 predictors plus intercept and 8 residual degrees of freedom.
- [ ] **Step 6: Commit** the isolated design-matrix implementation and tests.

### Task 2: Add the model fitter and statistical result contract

**Files:**
- Modify: `engine/src/process_intelligence_engine/modeling/fitters.py`
- Modify: `engine/src/process_intelligence_engine/main.py`
- Modify: `engine/src/process_intelligence_engine/prediction.py`
- Test: `engine/tests/test_categorical_doe_fitter.py`

**Interfaces:**
- Produces `fit_doe_categorical_factorial(df: pd.DataFrame, target: str, inputs: list[str], test_size: float = 0.3, random_state: int | None = None, include_three_factor_interaction: bool = False) -> ModelFit`.
- The returned `ModelFit.model_type` is `doe_categorical_factorial` and includes factor levels, coding metadata, model terms, train/test metrics, coefficients, and equation metadata in a backward-compatible DTO extension.
- Produces ANOVA-compatible coefficient statistics: coefficient, standard error, t statistic, p value, confidence interval, and term significance.

- [ ] **Step 1: Write failing tests** that fit the supplied DOE shape with `output-volume-CPK`, assert model type, term count, degrees of freedom, finite coefficients/statistics, and prediction on known levels.
- [ ] **Step 2: Run** `pytest engine/tests/test_categorical_doe_fitter.py -q` and confirm failure before implementation.
- [ ] **Step 3: Implement** the fitter using the Task 1 design matrix and least-squares/statistical calculations with the complete model fit used for inference; keep held-out metrics separate from inference residuals.
- [ ] **Step 4: Add** the model type to the engine registry/dispatch and prediction path, preserving level metadata and rejecting unknown levels.
- [ ] **Step 5: Add** explicit validation that the supplied design is estimable and report a readable error when combinations or rank are insufficient.
- [ ] **Step 6: Run** focused tests plus existing fitter, prediction, and serialization tests.
- [ ] **Step 7: Commit** the backend model implementation.

### Task 3: Expose model selection and factor metadata in the UI

**Files:**
- Modify: `src/lib/engine.ts`
- Modify: `src/features/model-center/ModelCenter.tsx`
- Modify: `src/i18n/zh-TW.json`
- Modify: `src/i18n/en.json`
- Modify: `src/i18n/es-MX.json`
- Test: `src/features/model-center/ModelCenter.test.tsx` or the repository’s established model-center test location

**Interfaces:**
- Adds `doe_categorical_factorial` to the model type union and model selector.
- Displays factor-level/coding metadata and design warnings before or beside the fit result.
- Keeps continuous DOE model explanations distinct from categorical factorial explanations.

- [ ] **Step 1: Write failing UI/type tests** for model selection, the categorical-model explanation, factor levels, and a missing-combination warning.
- [ ] **Step 2: Run** the focused frontend test/type check and confirm failure.
- [ ] **Step 3: Implement** the model option and IPC DTO typing without changing existing model options.
- [ ] **Step 4: Add** translated labels and guidance explaining that numeric-looking levels are treated as categories and that the default excludes ABC.
- [ ] **Step 5: Run** the focused frontend tests and `npm run build` or the repository’s standard frontend verification command.
- [ ] **Step 6: Commit** the UI and localization changes.

### Task 4: Replace misleading DOE charts with model-aware charts

**Files:**
- Modify: `src/features/model-center/ModelCenter.tsx`
- Modify: `engine/src/process_intelligence_engine/reporting/charting.py` if report-side chart data is generated there
- Test: `engine/tests/test_categorical_doe_charts.py`
- Test: frontend chart-data tests in the established model-center test location

**Interfaces:**
- Categorical model results provide predicted means by factor level and interaction slices from the fitted model, not coefficient endpoints.
- Pareto uses absolute standardized term statistics and a model-provided critical-value convention.
- Residual Q-Q data includes a fitted reference line; residual-vs-fitted and residual-vs-order use complete-fit residuals.

- [ ] **Step 1: Write failing tests** for factor-level main-effect means, non-empty AB/AC/BC interaction slices, Pareto term ordering, and Q-Q reference-line endpoints.
- [ ] **Step 2: Run** focused chart tests and verify failure.
- [ ] **Step 3: Implement** chart data from the categorical model’s prediction API; show actual level labels (`40/60/80`, etc.) on axes.
- [ ] **Step 4: Implement** interaction panels for AB, AC, and BC, matching the Minitab model’s two-factor terms and omitting ABC unless explicitly enabled.
- [ ] **Step 5: Correct** the residual normal-probability plot reference line and preserve the existing continuous-model chart behavior through model-type branching.
- [ ] **Step 6: Run** backend chart tests, frontend tests, and a manual 27-row smoke check against the supplied Minitab screenshots.
- [ ] **Step 7: Commit** chart changes.

### Task 5: Add an end-to-end Minitab comparison fixture

**Files:**
- Create: `engine/tests/fixtures/three_level_cpk_doe.csv` (sanitized copy of the supplied data, if repository policy permits test fixtures)
- Create: `engine/tests/test_minitab_compatible_cpk_doe.py`
- Modify: `README.md`
- Modify: `README_En.md`
- Modify: `docs/releases/<next-version>.md` or the current release-note file
- Modify: relevant deployment/user-guide documentation

**Interfaces:**
- The fixture maps `output-volume-CPK` as target and the three `input-*` columns as factors.
- The test asserts design shape, df structure, factor ordering, term presence, and stable qualitative significance ordering; it does not hard-code screenshots or claim exact Minitab numerical identity without a machine-readable Minitab export.

- [ ] **Step 1: Add** the fixture and a test documenting the exact target/factor mapping and 27 unique combinations.
- [ ] **Step 2: Assert** the expected model structure: 18 model df, 8 error df, A/B/C and AB/AC/BC terms, no ABC by default.
- [ ] **Step 3: Add** a comparison note explaining that exact coefficient/P-value parity requires matching Minitab coding, contrast, missing-value, and error-estimation settings.
- [ ] **Step 4: Update** README, release notes, and deployment/user instructions with the new model’s limits and workflow.
- [ ] **Step 5: Run** the full engine suite, frontend type/build checks, and the end-to-end fixture test.
- [ ] **Step 6: Commit** documentation and end-to-end coverage.

### Task 6: Final verification and release readiness

**Files:**
- No new source files; review all files from Tasks 1–5.

- [ ] **Step 1: Run** the complete relevant backend test suite.
- [ ] **Step 2: Run** frontend type checking/build and guide/i18n checks.
- [ ] **Step 3: Verify** old `doe_linear` and `doe_quadratic` snapshots/tests remain unchanged.
- [ ] **Step 4: Verify** a manual run using `DOE.xlsx` selects `output-volume-CPK`, shows the expected 18/8 df structure, and renders all three two-factor interaction plots.
- [ ] **Step 5: Record** any remaining numerical differences from Minitab as documented coding/contrast differences, not as unexplained parity claims.
- [ ] **Step 6: Commit** only after verification passes.

