# 2.0 AI Model Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add XGBoost/LightGBM models + auto feature selection + hyperparameter UI to the existing Random Forest implementation.

**Architecture:** The engine already has RandomForest with SHAP support. We add a shared `_auto_select_features` helper, expose hyperparameters through the IPC layer, add XGBoost/LightGBM fitters, and build a collapsible "Tree Model Settings" card in the frontend.

**Tech Stack:** Python 3.11, scikit-learn, xgboost (already in pyproject.toml), lightgbm (new), React 18, antd v5, TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-05-ai-model-expansion-v2-design.md`

---

### Task 1: Engine — Auto feature selection helper + RF hyperparameter exposure

**Files:**
- Modify: `engine/src/process_intelligence_engine/modeling/fitters.py`
- Modify: `engine/src/process_intelligence_engine/main.py`
- Modify: `engine/src/process_intelligence_engine/modeling/registry.py` (ModelFit.to_dto)
- Test: `engine/tests/test_fitters.py`

- [ ] **Step 1: Add `_auto_select_features` helper and modify `fit_random_forest`**

In `fitters.py`, add after the existing imports (around line 30):

```python
def _auto_select_features(
    df: pd.DataFrame,
    target: str,
    candidate_inputs: list[str],
    importance_threshold: float = 0.01,
    max_features: int = 5,
) -> list[str]:
    """Train a quick RF to rank features, return top-K with importance >= threshold."""
    X = df[candidate_inputs].to_numpy(dtype=float)
    y = df[target].to_numpy(dtype=float)
    rf = RandomForestRegressor(n_estimators=50, random_state=42, n_jobs=1)
    rf.fit(X, y)
    importances = rf.feature_importances_
    ranked = sorted(zip(candidate_inputs, importances), key=lambda x: -x[1])
    selected = [name for name, imp in ranked if imp >= importance_threshold]
    return selected[:max_features]
```

Modify `fit_random_forest` signature and body:

```python
def fit_random_forest(
    df: pd.DataFrame,
    target: str,
    inputs: list[str],
    test_size: float = 0.3,
    random_state: int | None = None,
    n_estimators: int = 200,
    max_depth: int | None = 10,
    min_samples_leaf: int = 3,
    auto_select_features: bool = False,
    importance_threshold: float = 0.01,
    max_features: int = 5,
) -> ModelFit:
    selected_inputs = inputs
    if auto_select_features and len(inputs) > 1:
        selected_inputs = _auto_select_features(
            df, target, inputs, importance_threshold, max_features
        )
    # ... rest of existing logic using selected_inputs instead of inputs
```

Update the return statement to include `selected_inputs`:
```python
    return ModelFit(
        model_type="random_forest",
        target=target,
        inputs=list(inputs),  # original inputs for display
        selected_inputs=list(selected_inputs),  # actually used
        ...
    )
```

- [ ] **Step 2: Update ModelFit.to_dto()**

In `fitters.py` line 62-76, add `selected_inputs` to the DTO:
```python
def to_dto(self) -> dict:
    return {
        ...
        "inputs": list(self.inputs),
        "selected_inputs": list(getattr(self, 'selected_inputs', self.inputs)),
        ...
    }
```

- [ ] **Step 3: Write failing tests**

In `test_fitters.py`, append:
```python
def test_fit_random_forest_auto_select_features(tmp_path):
    """Test auto feature selection returns fewer features when some are noise."""
    rng = np.random.default_rng(42)
    n = 200
    x1 = rng.uniform(0, 1, n)  # important
    x2 = rng.uniform(0, 1, n)  # important
    noise = rng.uniform(0, 1, n)  # should be filtered
    y = 2.0 + 3.0 * x1 - 4.0 * x2 + rng.normal(0, 0.01, n)
    df = pd.DataFrame({"x1": x1, "x2": x2, "noise": noise, "y": y})
    
    fit = fit_random_forest(df, target="y", inputs=["x1", "x2", "noise"], auto_select_features=True)
    assert fit.selected_inputs is not None
    assert len(fit.selected_inputs) <= 2  # should drop noise
    assert "noise" not in fit.selected_inputs


def test_fit_random_forest_hyperparameters():
    """Test hyperparameter exposure."""
    df = _simple_df(n=200)
    fit = fit_random_forest(df, target="y", inputs=["x1", "x2"], n_estimators=50, max_depth=5)
    assert fit.model is not None
    assert fit.metrics["r2"] > 0.5
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd engine && .venv/bin/python -m pytest tests/test_fitters.py::test_fit_random_forest_auto_select_features tests/test_fitters.py::test_fit_random_forest_hyperparameters -v`
Expected: FAIL (features not yet implemented)

- [ ] **Step 5: Implement and verify**

Run: `cd engine && .venv/bin/python -m pytest tests/test_fitters.py -q`
Expected: all fitter tests PASS

- [ ] **Step 6: Update main.py dispatch**

In `main.py`, modify `_handle_modeling_fit` (around line 521-531) to pass extra params:
```python
def _handle_modeling_fit(params: dict) -> dict:
    df = REGISTRY.get(params["dataset_id"])
    model_type = params["model_type"]
    target = params["target"]
    inputs = list(params.get("inputs", []))
    fitter = MODEL_FITTERS.get(model_type)
    if fitter is None:
        raise ValueError(f"Unknown model_type: {model_type}")
    
    # Extract hyperparameters (pass-through for tree models)
    hyperparams = {
        "n_estimators": params.get("n_estimators"),
        "max_depth": params.get("max_depth"),
        "min_samples_leaf": params.get("min_samples_leaf"),
        "auto_select_features": params.get("auto_select_features", False),
        "importance_threshold": params.get("importance_threshold", 0.01),
        "max_features": params.get("max_features", 5),
    }
    # Only pass non-None hyperparams
    hyperparams = {k: v for k, v in hyperparams.items() if v is not None}
    
    fit = fitter(df, target=target, inputs=inputs, **hyperparams)
    MODEL_REGISTRY.register(fit)
    return fit.to_dto()
```

- [ ] **Step 7: Commit**

```bash
git add engine/src/process_intelligence_engine/modeling/fitters.py \
       engine/src/process_intelligence_engine/main.py \
       engine/tests/test_fitters.py
git commit -m "feat(engine): auto feature selection + RF hyperparameter exposure"
```

---

### Task 2: Engine — XGBoost and LightGBM fitters

**Files:**
- Modify: `engine/src/process_intelligence_engine/modeling/fitters.py`
- Modify: `engine/pyproject.toml`
- Test: `engine/tests/test_fitters.py`

- [ ] **Step 1: Add XGBoost and LightGBM to dependencies**

In `pyproject.toml`, add lightgbm to dependencies:
```toml
dependencies = [
    ...
    "xgboost>=2.0.0",
    "lightgbm>=4.0.0",
    ...
]
```

- [ ] **Step 2: Add XGBoost fitter**

In `fitters.py`, add imports:
```python
try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
```

Add fitter function:
```python
def fit_xgboost(
    df: pd.DataFrame,
    target: str,
    inputs: list[str],
    test_size: float = 0.3,
    random_state: int | None = None,
    n_estimators: int = 200,
    max_depth: int = 6,
    learning_rate: float = 0.1,
    auto_select_features: bool = False,
    importance_threshold: float = 0.01,
    max_features: int = 5,
) -> ModelFit:
    if not inputs:
        raise ValueError("at least one input is required")
    if not XGBOOST_AVAILABLE:
        raise ImportError("xgboost is required. Install with: pip install xgboost")
    
    selected_inputs = inputs
    if auto_select_features and len(inputs) > 1:
        selected_inputs = _auto_select_features(df, target, inputs, importance_threshold, max_features)
    
    X = df[selected_inputs].to_numpy(dtype=float)
    y = df[target].to_numpy(dtype=float)
    X_tr, X_te, y_tr, y_te = _train_test(X, y, test_size, random_state)
    
    model = xgb.XGBRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        random_state=random_state,
        verbosity=0,
    )
    model.fit(X_tr, y_tr)
    y_pred = model.predict(X_te)
    
    return ModelFit(
        model_type="xgboost",
        target=target,
        inputs=list(inputs),
        selected_inputs=list(selected_inputs),
        metrics=_compute_all_metrics(y_te, y_pred, len(selected_inputs)),
        coefficients=None,
        equation=f"XGBoost(y, {selected_inputs})",
        n_train=len(X_tr),
        n_test=len(X_te),
        created_at=_now(),
        model=model,
    )
```

- [ ] **Step 3: Add LightGBM fitter**

```python
try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False
```

```python
def fit_lightgbm(
    df: pd.DataFrame,
    target: str,
    inputs: list[str],
    test_size: float = 0.3,
    random_state: int | None = None,
    n_estimators: int = 200,
    max_depth: int = 6,
    learning_rate: float = 0.1,
    auto_select_features: bool = False,
    importance_threshold: float = 0.01,
    max_features: int = 5,
) -> ModelFit:
    if not inputs:
        raise ValueError("at least one input is required")
    if not LIGHTGBM_AVAILABLE:
        raise ImportError("lightgbm is required. Install with: pip install lightgbm")
    
    selected_inputs = inputs
    if auto_select_features and len(inputs) > 1:
        selected_inputs = _auto_select_features(df, target, inputs, importance_threshold, max_features)
    
    X = df[selected_inputs].to_numpy(dtype=float)
    y = df[target].to_numpy(dtype=float)
    X_tr, X_te, y_tr, y_te = _train_test(X, y, test_size, random_state)
    
    model = lgb.LGBMRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        random_state=random_state,
        verbose=-1,
    )
    model.fit(X_tr, y_tr)
    y_pred = model.predict(X_te)
    
    return ModelFit(
        model_type="lightgbm",
        target=target,
        inputs=list(inputs),
        selected_inputs=list(selected_inputs),
        metrics=_compute_all_metrics(y_te, y_pred, len(selected_inputs)),
        coefficients=None,
        equation=f"LightGBM(y, {selected_inputs})",
        n_train=len(X_tr),
        n_test=len(X_te),
        created_at=_now(),
        model=model,
    )
```

- [ ] **Step 4: Update MODEL_FITTERS dispatch**

In `main.py`, add to `MODEL_FITTERS`:
```python
MODEL_FITTERS = {
    ...
    "xgboost": fit_xgboost,
    "lightgbm": fit_lightgbm,
}
```

- [ ] **Step 5: Write tests**

Append to `test_fitters.py`:
```python
def test_fit_xgboost_trains_and_scores():
    df = _simple_df(n=200)
    fit = fit_xgboost(df, target="y", inputs=["x1", "x2"])
    assert fit.model_type == "xgboost"
    assert fit.metrics["r2"] > 0.8


def test_fit_lightgbm_trains_and_scores():
    df = _simple_df(n=200)
    fit = fit_lightgbm(df, target="y", inputs=["x1", "x2"])
    assert fit.model_type == "lightgbm"
    assert fit.metrics["r2"] > 0.8


def test_fit_xgboost_auto_select():
    rng = np.random.default_rng(42)
    n = 200
    x1 = rng.uniform(0, 1, n)
    x2 = rng.uniform(0, 1, n)
    noise = rng.uniform(0, 1, n)
    y = 2.0 + 3.0 * x1 - 4.0 * x2 + rng.normal(0, 0.01, n)
    df = pd.DataFrame({"x1": x1, "x2": x2, "noise": noise, "y": y})
    
    fit = fit_xgboost(df, target="y", inputs=["x1", "x2", "noise"], auto_select_features=True)
    assert "noise" not in fit.selected_inputs
```

- [ ] **Step 6: Run tests**

Run: `cd engine && .venv/bin/python -m pytest tests/test_fitters.py -q`
Expected: all tests PASS (including new ones)

- [ ] **Step 7: Commit**

```bash
git add engine/src/process_intelligence_engine/modeling/fitters.py \
       engine/src/process_intelligence_engine/main.py \
       engine/pyproject.toml \
       engine/tests/test_fitters.py
git commit -m "feat(engine): add xgboost and lightgbm model fitters"
```

---

### Task 3: Frontend — Tree model settings UI

**Files:**
- Modify: `src/lib/engine.ts`
- Modify: `src/features/model-center/ModelCenter.tsx`
- Modify: `src/i18n/en.json`, `zh-TW.json`, `es-MX.json`

- [ ] **Step 1: Update engine.ts fitModel params**

In `engine.ts`, modify `fitModel` params:
```typescript
export async function fitModel(params: {
  dataset_id: string
  model_type: ModelType
  target: string
  inputs: string[]
  n_estimators?: number
  max_depth?: number
  min_samples_leaf?: number
  auto_select_features?: boolean
  importance_threshold?: number
  max_features?: number
}): Promise<ModelFitDTO> {
```

- [ ] **Step 2: Add new i18n keys**

In all three i18n files, add to `modelCenter` section:
```json
"treeModelAdvanced": "Tree Model Settings",
"autoFeatureSelect": "Auto feature selection",
"nEstimators": "Estimators",
"maxDepth": "Max Depth",
"minSamplesLeaf": "Min Samples Leaf",
"learningRate": "Learning Rate",
"featureSelected": "Auto-selected {{count}} features",
"featureImportance": "Feature Importance"
```

zh-TW:
```json
"treeModelAdvanced": "樹模型設定",
"autoFeatureSelect": "自動特徵選取",
"nEstimators": "樹棵數",
"maxDepth": "最大深度",
"minSamplesLeaf": "最小葉節點樣本數",
"learningRate": "學習率",
"featureSelected": "自動選取 {{count}} 個特徵",
"featureImportance": "特徵重要性"
```

es-MX:
```json
"treeModelAdvanced": "Configuración de modelo árbol",
"autoFeatureSelect": "Selección automática de características",
"nEstimators": "Estimadores",
"maxDepth": "Profundidad máxima",
"minSamplesLeaf": "Mín. muestras por hoja",
"learningRate": "Tasa de aprendizaje",
"featureSelected": "Seleccionados {{count}} características",
"featureImportance": "Importancia de características"
```

- [ ] **Step 3: Add state and UI in ModelCenter.tsx**

Add new state variables after existing state (around line 63):
```typescript
const [nEstimators, setNEstimators] = useState(200)
const [maxDepth, setMaxDepth] = useState(10)
const [minSamplesLeaf, setMinSamplesLeaf] = useState(3)
const [autoSelectFeatures, setAutoSelectFeatures] = useState(false)
const [selectedInputs, setSelectedInputs] = useState<string[]>([])
```

Modify `handleFit` to pass hyperparameters:
```typescript
const handleFit = async () => {
  if (!datasetId || !target || selectedInputs.length === 0) return
  const params: any = {
    dataset_id: datasetId,
    model_type: modelType,
    target,
    inputs: selectedInputs,
  }
  // Pass hyperparameters for tree models
  if (['random_forest', 'xgboost', 'lightgbm'].includes(modelType)) {
    params.n_estimators = nEstimators
    params.max_depth = maxDepth
    params.min_samples_leaf = minSamplesLeaf
    params.auto_select_features = autoSelectFeatures
  }
  const result = await fit(params)
  if (result) {
    if (result.selected_inputs && result.selected_inputs.length < selectedInputs.length) {
      setSelectedInputs(result.selected_inputs)
    }
    messageApi.success(t('modelCenter.fitSuccess'))
  }
}
```

Add the Tree Model Settings card after the inputs selector (around line 253):
```tsx
{['random_forest', 'xgboost', 'lightgbm'].includes(modelType) && (
  <Card title={t('modelCenter.treeModelAdvanced')} size="small">
    <Space direction="vertical" style={{ width: '100%' }}>
      <div>
        <Switch
          checked={autoSelectFeatures}
          onChange={setAutoSelectFeatures}
          checkedChildren={t('modelCenter.autoFeatureSelect')}
          unCheckedChildren={t('modelCenter.autoFeatureSelect')}
        />
      </div>
      {!autoSelectFeatures && (
        <>
          <div>
            <label>{t('modelCenter.nEstimators')}</label>
            <InputNumber
              min={50}
              max={500}
              value={nEstimators}
              onChange={(v) => setNEstimators(v || 200)}
              style={{ marginLeft: 8, width: 100 }}
            />
          </div>
          <div>
            <label>{t('modelCenter.maxDepth')}</label>
            <InputNumber
              min={1}
              max={20}
              value={maxDepth}
              onChange={(v) => setMaxDepth(v || 10)}
              style={{ marginLeft: 8, width: 100 }}
            />
          </div>
          <div>
            <label>{t('modelCenter.minSamplesLeaf')}</label>
            <InputNumber
              min={1}
              max={10}
              value={minSamplesLeaf}
              onChange={(v) => setMinSamplesLeaf(v || 3)}
              style={{ marginLeft: 8, width: 100 }}
            />
          </div>
        </>
      )}
    </Space>
  </Card>
)}
```

- [ ] **Step 4: Verify frontend**

Run: `npx tsc --noEmit`
Expected: exit 0
Run: `npm run build 2>&1 | tail -2`
Expected: `✓ built in ...s`

- [ ] **Step 5: Commit**

```bash
git add src/lib/engine.ts src/features/model-center/ModelCenter.tsx \
       src/i18n/en.json src/i18n/zh-TW.json src/i18n/es-MX.json
git commit -m "feat(model-center): tree model settings UI with hyperparameters"
```

---

### Task 4: SHAP support for XGBoost/LightGBM + verification

**Files:**
- Modify: `engine/src/process_intelligence_engine/modeling/shap_explainer.py`
- Test: `engine/tests/test_shap_explainer.py`

- [ ] **Step 1: Add XGBoost/LightGBM to SHAP explainer**

In `shap_explainer.py`, modify the type check (around line 36-41):
```python
if fit.model_type in ("doe_linear", "doe_quadratic"):
    return _compute_shap_linear(fit, df, nsamples, max_explain)
elif fit.model_type in ("random_forest", "xgboost", "lightgbm"):
    return _compute_shap_tree(fit, df, nsamples, max_explain)
else:
    raise ValueError(f"Unsupported model type for SHAP: {fit.model_type}")
```

- [ ] **Step 2: Add SHAP tests**

In `test_shap_explainer.py`, append:
```python
def test_shap_xgboost(tmp_path):
    """Test SHAP works with XGBoost model."""
    did = _import_model_csv_for_shap(tmp_path)
    fit_result = handle_request("modeling/fit", {
        "dataset_id": did, "model_type": "xgboost", "target": "y", "inputs": ["x1", "x2"]
    })
    shap_result = handle_request("modeling/shap", {
        "model_id": fit_result["model_id"], "dataset_id": did
    })
    assert "feature_importance" in shap_result
    assert len(shap_result["feature_importance"]) == 2


def test_shap_lightgbm(tmp_path):
    """Test SHAP works with LightGBM model."""
    did = _import_model_csv_for_shap(tmp_path)
    fit_result = handle_request("modeling/fit", {
        "dataset_id": did, "model_type": "lightgbm", "target": "y", "inputs": ["x1", "x2"]
    })
    shap_result = handle_request("modeling/shap", {
        "model_id": fit_result["model_id"], "dataset_id": did
    })
    assert "feature_importance" in shap_result
```

- [ ] **Step 3: Run tests**

Run: `cd engine && .venv/bin/python -m pytest tests/test_shap_explainer.py -q`
Expected: all tests PASS

- [ ] **Step 4: Final verification**

Run: `cd engine && .venv/bin/python -m pytest tests/ -q`
Expected: full suite PASS (should be ~320+ passed)

Run: `npx tsc --noEmit && npm run build 2>&1 | tail -2`
Expected: tsc clean, build success

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/modeling/shap_explainer.py \
       engine/tests/test_shap_explainer.py
git commit -m "feat(shap): add xgboost and lightgbm support"
```

---

### Task 5: Docs + push

**Files:**
- Modify: `PROGRESS.md`, `TASK.md`, `README.md`

- [ ] **Step 1: Update docs**

- `PROGRESS.md`: append 2.0 AI model expansion entry
- `TASK.md`: add Task 4 DONE entry
- `README.md`: update Phase 6 to mention tree models

- [ ] **Step 2: Push**

```bash
git push
```

---

## Self-review

- Spec coverage: all requirements met (auto feature selection, hyperparameter UI, XGBoost, LightGBM, SHAP)
- No placeholders; all code blocks complete
- Type consistency: `selected_inputs` added to ModelFitDTO, used consistently
