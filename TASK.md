# TASK.md

### Phase 3b-4 — 交互作用分析
- Task 1: `interactions.py` — 因子效應分解計算 (commit `451cb64`)
- Task 2: `main.py` + `engine.ts` — IPC handler + API wrapper (commit `07824d3`)
- Task 3: `ModelCenter.tsx` — 熱圖 UI + i18n (commit `9632e7e`)
- Task 4: 驗證 — 117 tests (89% coverage), tsc/build clean

### Phase 3b-5 — SHAP 可解釋性
- Task 1: `shap_explainer.py` — SHAP 值計算 (commit `826986c`)
- Task 2: `main.py` + `engine.ts` — IPC handler + API wrapper (commit `5ef27f3`)
- Task 3: `ModelCenter.tsx` — 特徵重要性圖 + SHAP 摘要圖 (commit `866699e`)
- Task 4: 驗證 — 123 tests (89% coverage), tsc/build clean

### Phase 3b-7 — 外插風險評分
- Task 1: `extrapolation.py` — 外插風險評分 (commit `a738613`)
- Task 2: `main.py` + `engine.ts` — IPC handler + API wrapper (commit `de32eff`)
- 驗證 — 131 tests pass (89% coverage), tsc/build clean

## Completed

### Phase 4 — Validation Experiment Recommendation
- Task 4: `main.py` + `engine.ts` — IPC handler `modeling/validation/full` with model comparison + experiment recommendation + `test_main_validation_full.py` (commit `6ad1f04`)
- Task 5: `ModelCenter.tsx` — Full Validation UI card with model comparison table, residual diagnostics, experiment recommendations + i18n (commit `6ad1f04`)
- 驗證 — 148 tests pass (89% coverage), tsc/build clean

### Phase 4 — Model Selection
- Task 2: `model_selection.py` — multi-model comparison with CV and composite scoring (commit `a9ad6ec`)
- Task 3: `experiment_recommendation.py` — experiment recommendation engine (commit `572a511`)
- 驗證 — 147 tests pass (88% coverage)

### Phase 3b-8 — Validation & Residual Analysis
- Task 1: `validation.py` — cross-validation, residual analysis, experiment recommendations (commit `89b397c`)
- Task 2: `main.py` + `engine.ts` — IPC handler `modeling/validation/analyze` + frontend `analyzeValidation` API (commit `6f1a4d6`)
- Task 3: Enhanced residual analysis — Q-Q plot data, residuals vs predicted, Durbin-Watson statistic (commit `02e5125`)
- 驗證 — 141 tests pass (88% coverage), tsc/build clean

### Phase 3a — Model Center Engine Core
- Task 1: `metrics.py` — RMSE/MSE/MAE/R²/Adjusted R² (commit `da6079d`)
- Task 2: `fitters.py` — DOE linear/quadratic + random forest + residual hybrid (commits `28c8c55`, `419ea2b`, `d677820`)
- Task 3: `registry.py` — immutable model versions + status machine (commit `68c36ef`, fix `ce94297`)
- Task 4: `main.py` — IPC handlers modeling/fit, modeling/list, modeling/transition (commits `be9d996`, `82ae1bb`)
- Task 5: `engine.ts` — frontend modeling types + API (commit `ff735a6`)
- Task 6: 驗證 + 文件 — 93 tests, 88% coverage, tsc/build/cargo clean

### Phase 3b-1 — Model Center UI
- Task 1: `modelStore.ts` — Zustand store (commit `6e2485a`, fix `4942008`)
- Task 2: `ModelCenter.tsx` — page component (commit `c2d611d`)
- Task 3: `App.tsx` — routing (commit `239a003`)
- Task 4: i18n en/zh-TW (commit `239a003`)
- Task 5: 驗證 — tsc/build clean

### Phase 3b-2 — Model Comparison Enhancement
- Checkbox row selection + Compare button + comparison Card + best-value highlighting (commit `70e9289`)

### Phase 3b-3 — DOE Design Library
- Task 1: Full Factorial + Fractional Factorial (commits `26ba9da`, `a04ebd3`)
- Task 2: CCD + Box-Behnken (commit `eb7c247`)
- Task 3: D-optimal + Taguchi L4/L8/L9/L16 (commit `31be710`)
- Task 4: IPC handler `modeling/doe/generate` + frontend `generateDOEDesign` API (commit `bf93182`)
- Task 5: 驗證 — 111 tests, tsc/build clean

### Phase 3b-4 — 交互作用分析
- Task 1: `interactions.py` — two-factor interaction strength (commit `451cb64`)
- Task 2: IPC handler `modeling/interactions/compute` + frontend `computeInteractions` API (commit `07824d3`)
- 驗證 — 117 tests pass, tsc clean

### Phase 3b-5 — SHAP 可解釋性
- Task 1: IPC handler `modeling/shap/explain` + frontend `computeSHAP` API (commit `5ef27f3`)
- Task 2: `ModelCenter.tsx` — SHAP 分析 Card（計算按鈕 + 特徵重要性圖 + SHAP summary 圖）+ i18n (commit `866699e`)
- 驗證 — 123 tests pass, tsc/build clean

### Phase 3b-7 — 外插風險評分
- Task 1: `extrapolation.py` — extrapolation risk scoring (commit `a738613`)
- Task 2: `main.py` + `engine.ts` — IPC handler + API wrapper (commit `de32eff`)
- Task 3: `ModelCenter.tsx` — extrapolation risk card (check button + risk score + factor breakdown) + i18n (commit `b6aa26d`)
- 驗證 — 131 tests pass (89% coverage), tsc/build clean

## In Progress
- None

## Pending
- None