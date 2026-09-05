# 2.0 AI 模型擴充（Random Forest 完善 + XGBoost / LightGBM）— 設計規格 v1.0

日期：2026-09-05
狀態：設計討論中

## 目標

在既有 DOE 線性/二次模型之上，擴充樹模型家族（Random Forest、XGBoost、LightGBM），並補上目前缺失的：
1. 超參數可調 UI
2. 自動特徵選取（基於樹模型 feature_importances_）
3. 新模型的引擎實作與 SHAP 解釋支援

## 範圍

### Included

**階段 1 — 完善 Random Forest**
- 引擎：`fit_random_forest` 加 `auto_select_features` 參數（基於 `feature_importances_` 選 top-K）
- 引擎：調整預設超參數（`n_estimators=200`, `max_depth=10`, `min_samples_leaf=3`）
- 前端：RF 模式時顯示進階設定區（超參數輸入 + 自動特徵選取 toggle）
- 前端：訓練結果顯示選取到的特徵清單
- i18n：~8 keys

**階段 2 — 新增 XGBoost / LightGBM**
- 引擎：`fit_xgboost` / `fit_lightgbm` 實作
- 依賴：`pyproject.toml` 加 `xgboost` / `lightgbm`
- 前端：MODEL_TYPES 加新選項，共用 RF 的超參數 UI
- SHAP：新模型支援 SHAP 解釋（XGBoost/LightGBM 有原生 feature_importance，SHAP 需额外安装 `shap` 樹模型 explainer）
- i18n：~6 keys

### Excluded

- 神經網路（MLP/CNN）— 留待後續版本
- AutoML 自動模型比較 — 留待後續版本
- 超參數自動搜尋（GridSearch/RandomSearch）— 留待後續版本（先手動調校）
- 非回歸模型（分類）— 当前 platform 只支援連續 output

## 設計

### 引擎 — 自動特徵選取

在 `fitters.py` 新增 helper：

```python
def _auto_select_features(
    df: pd.DataFrame,
    target: str,
    candidate_inputs: list[str],
    importance_threshold: float = 0.01,
    max_features: int = 5,
) -> list[str]:
    """Train a quick RF to rank features, return top-K with importance >= threshold."""
    from sklearn.ensemble import RandomForestRegressor
    X = df[candidate_inputs].to_numpy(dtype=float)
    y = df[target].to_numpy(dtype=float)
    rf = RandomForestRegressor(n_estimators=50, random_state=42, n_jobs=1)
    rf.fit(X, y)
    importances = rf.feature_importances_
    ranked = sorted(zip(candidate_inputs, importances), key=lambda x: -x[1])
    selected = [name for name, imp in ranked if imp >= importance_threshold]
    return selected[:max_features]
```

`fit_random_forest` 加參數：
```python
def fit_random_forest(
    df, target, inputs,
    auto_select_features: bool = False,
    importance_threshold: float = 0.01,
    max_features: int = 5,
    n_estimators: int = 200,
    max_depth: int = 10,
    min_samples_leaf: int = 3,
    random_state: int | None = 42,
    test_size: float = 0.3,
) -> ModelFit:
    if auto_select_features:
        inputs = _auto_select_features(df, target, inputs, importance_threshold, max_features)
    # ... existing logic
```

### 引擎 — XGBoost / LightGBM

新增 `fit_xgboost` / `fit_lightgbm`：

```python
def fit_xgboost(df, target, inputs, auto_select_features=False, ..., **kwargs) -> ModelFit:
    import xgboost as xgb
    # Similar structure to fit_random_forest
    # Store model for SHAP compatibility

def fit_lightgbm(df, target, inputs, auto_select_features=False, ..., **kwargs) -> ModelFit:
    import lightgbm as lgb
    # Similar structure
```

`main.py` dispatch table 加：
```python
"model_fit_handlers": {
    ...
    "xgboost": fit_xgboost,
    "lightgbm": fit_lightgbm,
}
```

### 引擎 — SHAP 支援

`shap_explainer.py` 加：
```python
elif fit.model_type in ("xgboost", "lightgbm"):
    explainer = shap.TreeExplainer(fit.model)
    shap_values = explainer.shap_values(X_test)
```

### 前端 — 超參數 UI

`ModelCenter.tsx`：當 `modelType === 'random_forest' || modelType === 'xgboost' || modelType === 'lightgbm'` 時，顯示進階區：

```tsx
{['random_forest', 'xgboost', 'lightgbm'].includes(modelType) && (
  <Card title={t('modelCenter.treeModelAdvanced')} size="small">
    <Space direction="vertical" style={{ width: '100%' }}>
      <Switch
        checked={autoSelectFeatures}
        onChange={setAutoSelectFeatures}
        label={t('modelCenter.autoFeatureSelect')}
      />
      {!autoSelectFeatures && (
        <>
          <Form.Item label={t('modelCenter.nEstimators')}>
            <InputNumber min={50} max={500} value={nEstimators} onChange={setNEstimators} />
          </Form.Item>
          <Form.Item label={t('modelCenter.maxDepth')}>
            <InputNumber min={1} max={20} value={maxDepth} onChange={setMaxDepth} />
          </Form.Item>
          <Form.Item label={t('modelCenter.minSamplesLeaf')}>
            <InputNumber min={1} max={10} value={minSamplesLeaf} onChange={setMinSamplesLeaf} />
          </Form.Item>
        </>
      )}
    </Space>
  </Card>
)}
```

### 前端 — 結果顯示

訓練完成後，若啟用自動特徵選取，顯示：
```tsx
{result.selected_inputs && result.selected_inputs.length < selectedInputs.length && (
  <Alert
    type="info"
    message={t('modelCenter.featureSelected', { count: result.selected_inputs.length })}
    description={result.selected_inputs.join(', ')}
  />
)}
```

### i18n 新增 keys

**en.json** (`modelCenter.*` section):
```json
"treeModelAdvanced": "Tree Model Settings",
"autoFeatureSelect": "Auto feature selection",
"nEstimators": "Estimators",
"maxDepth": "Max Depth",
"minSamplesLeaf": "Min Samples Leaf",
"featureSelected": "Auto-selected {{count}} features",
"featureImportance": "Feature Importance"
```

**zh-TW.json**:
```json
"treeModelAdvanced": "樹模型設定",
"autoFeatureSelect": "自動特徵選取",
"nEstimators": "樹棵數",
"maxDepth": "最大深度",
"minSamplesLeaf": "最小葉節點樣本數",
"featureSelected": "自動選取 {{count}} 個特徵",
"featureImportance": "特徵重要性"
```

**es-MX.json**:
```json
"treeModelAdvanced": "Configuración de modelo árbol",
"autoFeatureSelect": "Selección automática de características",
"nEstimators": "Estimadores",
"maxDepth": "Profundidad máxima",
"minSamplesLeaf": "Mín. muestras por hoja",
"featureSelected": "Seleccionados {{count}} características",
"featureImportance": "Importancia de características"
```

## 驗證

- 引擎 full suite：新增測試 ~10 支（RF auto-select, XGBoost fit, LightGBM fit, SHAP compatibility）
- `npx tsc --noEmit` clean
- `npm run build` 成功
- 三語 `modelCenter` key-set parity ok

## 依賴新增

`engine/pyproject.toml`:
```toml
[project.optional-dependencies]
ml = ["xgboost>=2.0", "lightgbm>=4.0"]
# 或加入 main dependencies
```

## Commit 預期

預計 2-3 commits：
1. `feat(engine): auto feature selection + RF hyperparameter exposure`
2. `feat(engine): add xgboost and lightgbm model fitters`
3. `feat(model-center): tree model UI + hyperparameter controls`

## Files changed（預期）

- `engine/src/process_intelligence_engine/modeling/fitters.py`
- `engine/src/process_intelligence_engine/modeling/shap_explainer.py`
- `engine/src/process_intelligence_engine/main.py`
- `engine/tests/test_modeling.py`（或新 test 檔）
- `src/features/model-center/ModelCenter.tsx`
- `src/i18n/en.json`, `zh-TW.json`, `es-MX.json`
- `engine/pyproject.toml`（依賴新增）
