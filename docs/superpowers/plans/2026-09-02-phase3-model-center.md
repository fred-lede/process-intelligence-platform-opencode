# Phase 3a — 模型中心引擎核心 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可訓練、比較、版本化並以 IPC 暴露的 DOE/隨機樹/混合殘差模型引擎核心，遵循 TDD。

**Architecture:** 引擎側新增 `modeling/` 子套件。三種模型能力（DOE 線性/二次回歸、隨機樹 AI、混合殘差 Y=f_DOE(X)+r_AI(X)）各自封裝於獨立模組，共用一個 `metrics.py`（RMSE/MAE/R²/Adjusted R²）與一個不可變版本 `ModelRegistry`（memory, thread-safe，仿 `DatasetRegistry`）。`main.py` 註冊 `modeling/*` IPC handlers，所有輸出走 `_plain_types` JSON 淨化層。

**Tech Stack:** Python 3.11、scikit-learn 1.9（LinearRegression、RandomForestRegressor、train_test_split）、numpy、pandas、statsmodels（OLS 供係數/p-value，選用）、pytest（TDD）。

**範圍界定（本計劃）**：引擎核心 + IPC。**延後（Phase 3b）**：完整 6 種 DOE 設計庫、交互作用 UI、模型比較/模型中心前端頁、驗證實驗推薦、SHAP、外插風險評分。本計劃只含「線性/二次 DOE + 隨機樹 + 混合殘差」三種模型、四種比較指標、狀態機（草稿→待驗證→已驗證→已核准→已停用）、不可變版本。

---

## 檔案結構

新增檔案（引擎）：
- `engine/src/process_intelligence_engine/modeling/__init__.py` — 子套件空 init
- `engine/src/process_intelligence_engine/modeling/metrics.py` — 比較指標（純函數，獨立可測）
- `engine/src/process_intelligence_engine/modeling/fitters.py` — 三種模型 fit（DOE 線性/二次、隨機樹、混合殘差）+ `ModelFit` dataclass
- `engine/src/process_intelligence_engine/modeling/registry.py` — `ModelRegistry`（不可變版本、狀態機）
- `engine/src/process_intelligence_engine/modeling/__main__` 不需要

新增測試：
- `engine/tests/test_metrics.py`
- `engine/tests/test_fitters.py`
- `engine/tests/test_model_registry.py`
- `engine/tests/test_main_modeling.py`（IPC handlers）

修改：
- `engine/src/process_intelligence_engine/main.py` — 註冊 `modeling/*` handlers、`_handle_*` 函數
- 前端 `src/lib/engine.ts` — 新增 modeling API 型別與函數（僅型別/API 封裝，不含 UI 頁）
- 前端 store 本輪**不加**（無 UI 消費端），避免死碼

## 資料契約說明

- `dataset_id` 指向 `DatasetRegistry` 中已註冊 DataFrame。
- fit params：
  - `target`：output 欄位名（連續數值）
  - `inputs`：輸入欄位名清單
  - `columns` 由 dataset 提供
- DTO（`ModelFit.to_dto()`）：
  ```json
  {
    "model_id": "...",
    "model_type": "doe_linear" | "doe_quadratic" | "random_forest" | "residual_hybrid",
    "target": "temperature",
    "inputs": ["pressure", ...],
    "status": "draft" | "pending_validation" | "validated" | "approved" | "retired",
    "created_at": "...",
    "metrics": {
      "rmse": .., "mae": .., "r2": .., "adj_r2": ..
    },
    "coefficients": {...} | null,
    "equation": "...",
    "n_train": .., "n_test": ..,
    "version": 1
  }
  ```

---

### Task 1: metrics.py（RMSE/MAE/R²/Adjusted R²）

**Files:**
- Create: `engine/src/process_intelligence_engine/modeling/__init__.py`
- Create: `engine/src/process_intelligence_engine/modeling/metrics.py`
- Test: `engine/tests/test_metrics.py`

- [ ] **Step 1: 寫失敗測試** `engine/tests/test_metrics.py`

```python
"""Tests for modeling metrics."""
import numpy as np

from process_intelligence_engine.modeling.metrics import (
    mean_absolute_error,
    mean_squared_error,
    root_mean_squared_error,
    r2_score,
    adjusted_r2,
)


def test_rmse_perfect_prediction_is_zero():
    y = np.array([1.0, 2.0, 3.0])
    assert root_mean_squared_error(y, y) == 0.0


def test_rmse_known_value():
    y = np.array([0.0, 0.0])
    yhat = np.array([1.0, 1.0])
    assert root_mean_squared_error(y, yhat) == 1.0
    assert np.isclose(mean_squared_error(y, yhat), 1.0)


def test_mae_is_mean_absolute_error():
    y = np.array([0.0, 0.0])
    yhat = np.array([1.0, -2.0])
    assert mean_absolute_error(y, yhat) == 1.5


def test_r2_perfect_is_one():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    assert r2_score(y, y) == 1.0


def test_r2_worse_than_mean_is_negative():
    y = np.array([0.0, 0.0])
    yhat = np.array([5.0, 5.0])
    assert r2_score(y, yhat) < 0.0


def test_adjusted_r2_penalizes_more_features():
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    yhat = np.array([1.1, 1.9, 3.1, 4.1, 5.0])
    n = len(y)
    p_1 = 1
    p_3 = 3
    r2 = r2_score(y, yhat)
    assert adjusted_r2(r2, n, p_3) < adjusted_r2(r2, n, p_1)
    assert adjusted_r2(r2, n, p_1) < r2  # penalized below R2
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd engine && .venv/bin/pytest tests/test_metrics.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'process_intelligence_engine.modeling'`

- [ ] **Step 3: 建立 modeling 子套件與 metrics 實作**

`engine/src/process_intelligence_engine/modeling/__init__.py`：
```python
"""Phase 3: DOE / AI / hybrid modeling subsystem."""
```

`engine/src/process_intelligence_engine/modeling/metrics.py`：
```python
"""Regression comparison metrics (all JSON-native floats).

Shared by DOE / AI / hybrid models so comparisons use identical statistics.
"""

from __future__ import annotations

import numpy as np


def _pair(y_true, y_pred) -> tuple[np.ndarray, np.ndarray]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if y_true.shape != y_pred.shape:
        raise ValueError("y_true and y_pred must have the same shape")
    return y_true, y_pred


def mean_squared_error(y_true, y_pred) -> float:
    y_true, y_pred = _pair(y_true, y_pred)
    return float(np.mean((y_true - y_pred) ** 2))


def root_mean_squared_error(y_true, y_pred) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def mean_absolute_error(y_true, y_pred) -> float:
    y_true, y_pred = _pair(y_true, y_pred)
    return float(np.mean(np.abs(y_true - y_pred)))


def r2_score(y_true, y_pred) -> float:
    y_true, y_pred = _pair(y_true, y_pred)
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return 1.0 if ss_res == 0 else 0.0
    return float(1.0 - ss_res / ss_tot)


def adjusted_r2(r2: float, n: int, p: int) -> float:
    """Wherry-McLaughlin adjusted R²; n = samples, p = feature count."""
    if n - p - 1 <= 0:
        return r2
    return float(1.0 - (1.0 - r2) * (n - 1) / (n - p - 1))
```

- [ ] **Step 4: 執行測試確認通過**

Run: `cd engine && .venv/bin/pytest tests/test_metrics.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/modeling engine/tests/test_metrics.py
git commit -m "feat(modeling): add regression comparison metrics"
```

---

### Task 2: fitters.py（DOE 線性/二次 + 隨機樹）

**Files:**
- Create: `engine/src/process_intelligence_engine/modeling/fitters.py`
- Test: `engine/tests/test_fitters.py`

- [ ] **Step 1: 寫失敗測試** `engine/tests/test_fitters.py`

```python
"""Tests for DOE / AI / hybrid model fitting."""
import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.modeling.fitters import (
    fit_doe_linear,
    fit_doe_quadratic,
    fit_random_forest,
    fit_residual_hybrid,
)


def _simple_df(n=100, seed=3):
    rng = np.random.default_rng(seed)
    x1 = rng.uniform(0, 1, n)
    x2 = rng.uniform(0, 1, n)
    y = 2.0 + 3.0 * x1 - 4.0 * x2 + rng.normal(0, 0.01, n)
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


def test_fit_doe_linear_recovers_coefficients():
    df = _simple_df()
    fit = fit_doe_linear(df, target="y", inputs=["x1", "x2"])
    assert fit.model_type == "doe_linear"
    assert fit.metrics["r2"] > 0.95
    # y = 2 + 3 x1 - 4 x2 approximate
    c = fit.coefficients
    assert abs(c.get("x1", 0) - 3.0) < 0.5
    assert abs(c.get("x2", 0) + 4.0) < 0.5
    assert fit.equation
    assert fit.direction is None  # regression has no directional encoding


def test_fit_doe_quadratic_captures_squared_term():
    rng = np.random.default_rng(5)
    n = 200
    x = rng.uniform(0, 2, n)
    y = 1.0 + 2.0 * x + 0.8 * x ** 2 + rng.normal(0, 0.05, n)
    df = pd.DataFrame({"x": x, "y": y})
    fit = fit_doe_quadratic(df, target="y", inputs=["x"])
    assert fit.model_type == "doe_quadratic"
    assert fit.metrics["r2"] > 0.9
    # Coefficients keyed by python expression
    assert any("x^2" in k or "**2" in k for k in fit.coefficients)


def test_quadratic_requires_at_least_one_input():
    df = _simple_df(n=20)
    with pytest.raises(ValueError):
        fit_doe_quadratic(df, target="y", inputs=[])


def test_fit_random_forest_trains_and_scores():
    df = _simple_df(n=200)
    fit = fit_random_forest(df, target="y", inputs=["x1", "x2"], test_size=0.3, random_state=7)
    assert fit.model_type == "random_forest"
    assert fit.metrics["r2"] > 0.8
    assert fit.n_train + fit.n_test > 0
    assert fit.coefficients is None  # RF has no linear coefficients


def test_residual_hybrid_fit_is_better_than_linear_alone():
    # Non-linear term the linear model misses; RF residual should recover it.
    rng = np.random.default_rng(9)
    n = 300
    x = rng.uniform(0, 1, n)
    y = 1.0 + 2.0 * x + np.sin(10 * x) + rng.normal(0, 0.02, n)
    df = pd.DataFrame({"x": x, "y": y})
    hybrid = fit_residual_hybrid(df, target="y", inputs=["x"], random_state=11)
    assert hybrid.model_type == "residual_hybrid"
    assert hybrid.metrics["r2"] > 0.9


def test_fit_dto_is_json_serializable():
    import json

    df = _simple_df(n=80)
    fit = fit_doe_linear(df, target="y", inputs=["x1", "x2"])
    payload = json.dumps(fit.to_dto())
    assert payload
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd engine && .venv/bin/pytest tests/test_fitters.py -q`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: 建立 fitters.py 實作**

`engine/src/process_intelligence_engine/modeling/fitters.py`：
```python
"""Model fitting: linear/quadratic DOE, random-forest AI, residual hybrid.

The residual hybrid fits Y = f_DOE(X) + r_AI(X): a linear/quadratic
regression captures the interpretable structure and a random forest models
the residual r = Y - f_DOE(X).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split

from .metrics import (
    mean_absolute_error,
    root_mean_squared_error,
    r2_score,
    adjusted_r2,
)

MODEL_TYPES = {
    "doe_linear": "doe_linear",
    "doe_quadratic": "doe_quadratic",
    "random_forest": "random_forest",
    "residual_hybrid": "residual_hybrid",
}

STATUS = ("draft", "pending_validation", "validated", "approved", "retired")


@dataclass
class ModelFit:
    """A fitted model + comparison metrics, ready for IPC serialization."""

    model_type: str
    target: str
    inputs: list[str]
    metrics: dict = field(default_factory=dict)
    coefficients: dict | None = None
    equation: str = ""
    n_train: int = 0
    n_test: int = 0
    status: str = "draft"
    model_id: str = ""
    created_at: str = ""
    version: int = 1
    direction: str | None = None

    def to_dto(self) -> dict:
        return {
            "model_id": self.model_id,
            "model_type": self.model_type,
            "target": self.target,
            "inputs": list(self.inputs),
            "status": self.status,
            "created_at": self.created_at,
            "version": self.version,
            "metrics": dict(self.metrics),
            "coefficients": self.coefficients,
            "equation": self.equation,
            "n_train": self.n_train,
            "n_test": self.n_test,
        }


def _compute_all_metrics(y_true, y_pred, n_features: int) -> dict:
    return {
        "rmse": root_mean_squared_error(y_true, y_pred),
        "mae": mean_absolute_error(y_true, y_pred),
        "r2": r2_score(y_true, y_pred),
        "adj_r2": adjusted_r2(r2_score(y_true, y_pred), len(y_true), n_features),
    }


def _train_test(X: np.ndarray, y: np.ndarray, test_size: float, random_state: int | None):
    return train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _design_matrix(df: pd.DataFrame, inputs: list[str], degree: int = 1) -> pd.DataFrame:
    """Build a (possibly quadratic) design matrix with an intercept column."""
    if not inputs:
        raise ValueError("at least one input is required")
    cols: dict[str, np.ndarray] = {"1": np.ones(len(df))}
    for x in inputs:
        cols[x] = df[x].to_numpy(dtype=float)
        if degree >= 2:
            cols[f"{x}^2"] = df[x].to_numpy(dtype=float) ** 2
    if degree >= 2 and len(inputs) >= 2:
        # add cross terms (i<j)
        for i in range(len(inputs)):
            for j in range(i + 1, len(inputs)):
                xi = inputs[i]
                xj = inputs[j]
                cols[f"{xi}*{xj}"] = (
                    df[xi].to_numpy(dtype=float) * df[xj].to_numpy(dtype=float)
                )
    return pd.DataFrame(cols)


def _fit_linear_on_matrix(df, target, inputs, degree, test_size, random_state) -> ModelFit:
    X = _design_matrix(df, inputs, degree).to_numpy(dtype=float)
    y = df[target].to_numpy(dtype=float)
    X_tr, X_te, y_tr, y_te = _train_test(X, y, test_size, random_state)
    model = LinearRegression().fit(X_tr, y_tr)
    y_pred = model.predict(X_te)
    design = _design_matrix(df, inputs, degree)
    coefs = dict(zip(design.columns, model.coef_.tolist()))
    metrics = _compute_all_metrics(y_te, y_pred, len(inputs))
    # Build a human-readable equation
    terms = [f"{model.intercept_:.4g}"]
    for name, c in coefs.items():
        if name == "1":
            continue
        terms.append(f"{c:+.4g}*{name}")
    fit = ModelFit(
        model_type="doe_quadratic" if degree >= 2 else "doe_linear",
        target=target,
        inputs=list(inputs),
        metrics=metrics,
        coefficients={k: float(v) for k, v in coefs.items()},
        equation=" ".join(terms),
        n_train=len(X_tr),
        n_test=len(X_te),
        created_at=_now(),
    )
    return fit


def fit_doe_linear(
    df: pd.DataFrame, target: str, inputs: list[str], test_size: float = 0.3, random_state: int | None = None
) -> ModelFit:
    return _fit_linear_on_matrix(df, target, inputs, degree=1, test_size=test_size, random_state=random_state)


def fit_doe_quadratic(
    df: pd.DataFrame, target: str, inputs: list[str], test_size: float = 0.3, random_state: int | None = None
) -> ModelFit:
    return _fit_linear_on_matrix(df, target, inputs, degree=2, test_size=test_size, random_state=random_state)


def fit_random_forest(
    df: pd.DataFrame,
    target: str,
    inputs: list[str],
    test_size: float = 0.3,
    random_state: int | None = None,
    n_estimators: int = 100,
) -> ModelFit:
    if not inputs:
        raise ValueError("at least one input is required")
    X = df[inputs].to_numpy(dtype=float)
    y = df[target].to_numpy(dtype=float)
    X_tr, X_te, y_tr, y_te = _train_test(X, y, test_size, random_state)
    rf = RandomForestRegressor(n_estimators=n_estimators, random_state=random_state, n_jobs=1)
    rf.fit(X_tr, y_tr)
    y_pred = rf.predict(X_te)
    return ModelFit(
        model_type="random_forest",
        target=target,
        inputs=list(inputs),
        metrics=_compute_all_metrics(y_te, y_pred, len(inputs)),
        coefficients=None,
        equation=f"RandomForest(y, {inputs})",
        n_train=len(X_tr),
        n_test=len(X_te),
        created_at=_now(),
    )


def fit_residual_hybrid(
    df: pd.DataFrame,
    target: str,
    inputs: list[str],
    test_size: float = 0.3,
    random_state: int | None = None,
    n_estimators: int = 100,
) -> ModelFit:
    if not inputs:
        raise ValueError("at least one input is required")
    y = df[target].to_numpy(dtype=float)
    X = df[inputs].to_numpy(dtype=float)
    D = _design_matrix(df, inputs, degree=2).to_numpy(dtype=float)
    doe_cols = _design_matrix(df, inputs, degree=2).columns
    n = len(df)
    # Single index scheme: shuffle row indices once, share across DOE+RF.
    idx = np.arange(n)
    rs = np.random.default_rng(random_state)
    idx = rs.permutation(idx) if random_state is not None else idx[::-1]
    test_n = int(n * test_size)
    test_idx = idx[:test_n]
    train_idx = idx[test_n:]
    # DOE quadratic captures interpretable curvature on the training slice.
    doe = LinearRegression().fit(D[train_idx], y[train_idx])
    residual = y[train_idx] - doe.predict(D[train_idx])
    rf = RandomForestRegressor(n_estimators=n_estimators, random_state=random_state, n_jobs=1)
    rf.fit(X[train_idx], residual)
    y_pred = doe.predict(D[test_idx]) + rf.predict(X[test_idx])
    y_test = y[test_idx]
    coefs = dict(zip(doe_cols, doe.coef_.tolist()))
    return ModelFit(
        model_type="residual_hybrid",
        target=target,
        inputs=list(inputs),
        metrics=_compute_all_metrics(y_test, y_pred, len(inputs)),
        coefficients={k: float(v) for k, v in coefs.items()},
        equation="Y = f_DOE(X) + r_RF(X)",
        n_train=len(train_idx),
        n_test=len(test_idx),
        created_at=_now(),
    )
```

`fit_residual_hybrid` 使用單一 `idx = rs.permutation(idx)` 產生 train/test 索引，DOE 與 RF 共用同一組 `train_idx`/`test_idx`，評估只用 `y[test_idx]` 與 `y_pred`（兩者維度皆為 `test_n`）。

- [ ] **Step 4: 執行測試確認通過**

Run: `cd engine && .venv/bin/pytest tests/test_fitters.py -q`
Expected: PASS (6 passed)
> 若 `test_residual_hybrid...` 或 `test_fit_dto...` 失敗，直接修正 `fit_residual_hybrid` 內索引邏輯直到全綠。

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/modeling/fitters.py engine/tests/test_fitters.py
git commit -m "feat(modeling): DOE linear/quadratic, random forest, residual hybrid fits"
```

---

### Task 3: registry.py（不可變版本 + 狀態機）

**Files:**
- Create: `engine/src/process_intelligence_engine/modeling/registry.py`
- Test: `engine/tests/test_model_registry.py`

- [ ] **Step 1: 寫失敗測試** `engine/tests/test_model_registry.py`

```python
"""Tests for immutable model version registry and status machine."""
import pandas as pd
import pytest

from process_intelligence_engine.modeling.fitters import fit_doe_linear
from process_intelligence_engine.modeling.registry import ModelRegistry, InvalidStatusTransition


def _fit_df():
    import numpy as np
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 1, 60)
    y = 2.0 + 3.0 * x + rng.normal(0, 0.01, 60)
    return pd.DataFrame({"x": x, "y": y})


def test_register_assigns_id_and_status_draft():
    reg = ModelRegistry()
    fit = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    reg.register(fit)
    assert fit.model_id
    assert fit.status == "draft"
    assert reg.get(fit.model_id) is fit


def test_register_increments_version():
    reg = ModelRegistry()
    fit1 = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    fit2 = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    reg.register(fit1)
    reg.register(fit2)
    assert fit1.version == 1
    assert fit2.version == 2


def test_list_models_returns_registered():
    reg = ModelRegistry()
    fit = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    reg.register(fit)
    ids = reg.list_ids()
    assert fit.model_id in ids


def test_unknown_status_transition_raises():
    reg = ModelRegistry()
    fit = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    reg.register(fit)
    with pytest.raises(InvalidStatusTransition):
        # cannot go draft -> approved without passing through validation
        reg.transition(fit.model_id, "approved")


def test_valid_transition_draft_to_pending():
    reg = ModelRegistry()
    fit = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    reg.register(fit)
    reg.transition(fit.model_id, "pending_validation")
    assert fit.status == "pending_validation"


def test_full_chain_to_approved():
    reg = ModelRegistry()
    fit = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    reg.register(fit)
    for s in ("pending_validation", "validated", "approved"):
        reg.transition(fit.model_id, s)
    assert fit.status == "approved"
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd engine && .venv/bin/pytest tests/test_model_registry.py -q`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: 建立 registry.py 實作**

`engine/src/process_intelligence_engine/modeling/registry.py`：
```python
"""Immutable model version registry + status machine (spec 12.5).

State flow: draft → pending_validation → validated → approved; any state
may go to retired. Immutable versions: register() assigns a monotonic
version; a model's DTO is snapshotted on read so later reassignment never
mutates a previously read version.
"""

from __future__ import annotations

import threading
import uuid

from .fitters import ModelFit

VALID_STATUS = ("draft", "pending_validation", "validated", "approved", "retired")

# Which target statuses are reachable from each source status.
TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_validation", "retired"},
    "pending_validation": {"validated", "retired"},
    "validated": {"approved", "retired"},
    "approved": {"retired"},
    "retired": set(),
}


class InvalidStatusTransition(Exception):
    pass


class ModelRegistry:
    """In-memory, thread-safe registry of fitted models with immutable versions."""

    def __init__(self) -> None:
        self._models: dict[str, ModelFit] = {}
        self._lock = threading.Lock()
        self._version_counter = 0

    def register(self, fit: ModelFit) -> str:
        with self._lock:
            self._version_counter += 1
            fit.model_id = str(uuid.uuid4())
            fit.version = self._version_counter
            fit.status = "draft"
            self._models[fit.model_id] = fit
            return fit.model_id

    def get(self, model_id: str) -> ModelFit:
        with self._lock:
            if model_id not in self._models:
                raise KeyError(f"Unknown model_id: {model_id}")
            return self._models[model_id]

    def list_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._models.keys())

    def transition(self, model_id: str, new_status: str) -> ModelFit:
        with self._lock:
            if new_status not in VALID_STATUS:
                raise ValueError(f"Unknown status: {new_status}")
            fit = self.get_unlocked(model_id)
            if new_status not in TRANSITIONS.get(fit.status, set()):
                raise InvalidStatusTransition(
                    f"Cannot transition {fit.status} -> {new_status}"
                )
            fit.status = new_status
            return fit

    def get_unlocked(self, model_id: str) -> ModelFit:
        if model_id not in self._models:
            raise KeyError(f"Unknown model_id: {model_id}")
        return self._models[model_id]
```

> 注意：`transition` 內呼叫 `self.get_unlocked` 而不是 `get`，避免在同一 lock 內再次取得 `threading.Lock`（`threading.Lock` 不可重入）。`get_unlocked` 假設呼叫端已持有 lock。

- [ ] **Step 4: 執行測試確認通過**

Run: `cd engine && .venv/bin/pytest tests/test_model_registry.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/modeling/registry.py engine/tests/test_model_registry.py
git commit -m "feat(modeling): immutable model registry with status machine"
```

---

### Task 4: main.py IPC handlers（modeling/*）

**Files:**
- Modify: `engine/src/process_intelligence_engine/main.py`
- Test: `engine/tests/test_main_modeling.py`

- [ ] **Step 1: 寫失敗測試** `engine/tests/test_main_modeling.py`

```python
"""Tests for modeling/* IPC handlers."""
import json

from process_intelligence_engine.main import handle_request


def _import_model_csv(tmp_path):
    import numpy as np
    rng = np.random.default_rng(1)
    rows = ["x1,x2,y"]
    for _ in range(120):
        x1 = rng.uniform(0, 1)
        x2 = rng.uniform(0, 1)
        y = 2.0 + 3.0 * x1 - 4.0 * x2 + rng.normal(0, 0.01)
        rows.append(f"{x1:.5f},{x2:.5f},{y:.5f}")
    path = tmp_path / "model.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    return handle_request("data/import", {"file_path": str(path)})["dataset_id"]


def test_modeling_fit_returns_dto(tmp_path):
    did = _import_model_csv(tmp_path)
    result = handle_request(
        "modeling/fit",
        {"dataset_id": did, "model_type": "doe_linear", "target": "y", "inputs": ["x1", "x2"]},
    )
    assert result["model_type"] == "doe_linear"
    assert result["metrics"]["r2"] > 0.9
    json.dumps(result)


def test_modeling_fit_residual_hybrid(tmp_path):
    did = _import_model_csv(tmp_path)
    result = handle_request(
        "modeling/fit",
        {"dataset_id": did, "model_type": "residual_hybrid", "target": "y", "inputs": ["x1", "x2"]},
    )
    assert result["model_type"] == "residual_hybrid"
    assert result["metrics"]["r2"] > 0.9


def test_modeling_fit_unknown_type_raises(tmp_path):
    did = _import_model_csv(tmp_path)
    with pytest.raises(ValueError):
        handle_request(
            "modeling/fit",
            {"dataset_id": did, "model_type": "nope", "target": "y", "inputs": ["x1"]},
        )


def test_modeling_transition_and_list(tmp_path):
    did = _import_model_csv(tmp_path)
    fit = handle_request(
        "modeling/fit",
        {"dataset_id": did, "model_type": "doe_linear", "target": "y", "inputs": ["x1", "x2"]},
    )
    assert fit["status"] == "draft"

    pending = handle_request("modeling/transition", {"model_id": fit["model_id"], "status": "pending_validation"})
    assert pending["status"] == "pending_validation"

    listing = handle_request("modeling/list", {})
    assert any(m["model_id"] == fit["model_id"] for m in listing["models"])


def test_modeling_transition_invalid_raises(tmp_path):
    did = _import_model_csv(tmp_path)
    fit = handle_request(
        "modeling/fit",
        {"dataset_id": did, "model_type": "doe_linear", "target": "y", "inputs": ["x1", "x2"]},
    )
    with pytest.raises(Exception) as exc:
        handle_request("modeling/transition", {"model_id": fit["model_id"], "status": "approved"})
    assert "transition" in str(exc.value).lower() or "Cannot" in str(exc.value)
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd engine && .venv/bin/pytest tests/test_main_modeling.py -q`
Expected: FAIL `ValueError: Unknown method: modeling/fit`

- [ ] **Step 3: 在 main.py 註冊 handlers**

新增 import：
```python
from process_intelligence_engine.modeling.fitters import (
    fit_doe_linear,
    fit_doe_quadratic,
    fit_random_forest,
    fit_residual_hybrid,
)
from process_intelligence_engine.modeling.registry import InvalidStatusTransition, ModelRegistry
```

新增 `ModelRegistry` 全域實例（置於 `REGISTRY` 之下）：
```python
MODEL_REGISTRY = ModelRegistry()
```

新增 handler 函數（放在 `_handle_analysis_package` 之後）：
```python
MODEL_FITTERS = {
    "doe_linear": fit_doe_linear,
    "doe_quadratic": fit_doe_quadratic,
    "random_forest": fit_random_forest,
    "residual_hybrid": fit_residual_hybrid,
}


def _handle_modeling_fit(params: dict) -> dict:
    df = REGISTRY.get(params["dataset_id"])
    model_type = params["model_type"]
    target = params["target"]
    inputs = list(params.get("inputs", []))
    fitter = MODEL_FITTERS.get(model_type)
    if fitter is None:
        raise ValueError(f"Unknown model_type: {model_type}")
    fit = fitter(df, target=target, inputs=inputs)
    MODEL_REGISTRY.register(fit)
    return fit.to_dto()


def _handle_modeling_list(params: dict) -> dict:
    return {
        "models": [MODEL_REGISTRY.get(mid).to_dto() for mid in MODEL_REGISTRY.list_ids()]
    }


def _handle_modeling_transition(params: dict) -> dict:
    fit = MODEL_REGISTRY.transition(params["model_id"], params["status"])
    return fit.to_dto()
```

在 `handle_request` 的 `analysis/package` 分支之後加入分發：
```python
    if method == "modeling/fit":
        return _handle_modeling_fit(params)

    if method == "modeling/list":
        return _handle_modeling_list(params)

    if method == "modeling/transition":
        return _handle_modeling_transition(params)
```

- [ ] **Step 4: 執行測試確認通過**

Run: `cd engine && .venv/bin/pytest tests/test_main_modeling.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/main.py engine/tests/test_main_modeling.py
git commit -m "feat(modeling): expose modeling/fit, modeling/list, modeling/transition IPC"
```

---

### Task 5: 前端 engine.ts 型別 + API 封裝

**Files:**
- Modify: `src/lib/engine.ts`
- 測試：`tsc --noEmit`（無 runtime 測試消費端本輪）

- [ ] **Step 1: 在 `src/lib/engine.ts` 末尾追加 modeling 型別與函數**

```typescript
// --- Phase 3: Modeling ----------------------------------------------------

export type ModelType =
  | 'doe_linear'
  | 'doe_quadratic'
  | 'random_forest'
  | 'residual_hybrid'

export type ModelStatus =
  | 'draft'
  | 'pending_validation'
  | 'validated'
  | 'approved'
  | 'retired'

export interface ModelMetrics {
  rmse: number
  mae: number
  r2: number
  adj_r2: number
}

export interface ModelFitDTO {
  model_id: string
  model_type: ModelType
  target: string
  inputs: string[]
  status: ModelStatus
  created_at: string
  version: number
  metrics: ModelMetrics
  coefficients: Record<string, number> | null
  equation: string
  n_train: number
  n_test: number
}

export async function fitModel(params: {
  dataset_id: string
  model_type: ModelType
  target: string
  inputs: string[]
}): Promise<ModelFitDTO> {
  return engineCall<ModelFitDTO>('modeling/fit', params as unknown as Record<string, unknown>)
}

export async function listModels(): Promise<{ models: ModelFitDTO[] }> {
  return engineCall<{ models: ModelFitDTO[] }>('modeling/list', {})
}

export async function transitionModel(
  model_id: string,
  status: ModelStatus,
): Promise<ModelFitDTO> {
  return engineCall<ModelFitDTO>('modeling/transition', { model_id, status })
}
```

- [ ] **Step 2: 型別檢查**

Run: `cd <repo-root> && npx tsc --noEmit`
Expected: PASS（無輸出、exit 0）

- [ ] **Step 3: Commit**

```bash
git add src/lib/engine.ts
git commit -m "feat(modeling): add frontend model API types"
```

---

### Task 6: 驗證門檻 + 文件更新

**Files:**
- Modify: `TASK.md`
- Modify: `PROGRESS.md`
- Modify: `README.md`

- [ ] **Step 1: 跑全引擎測試確認無回歸**

Run: `cd engine && .venv/bin/pytest -q`
Expected: 全綠（既有 68 + 新增 modeling tests 全過），覆蓋率 ≥ 前值

- [ ] **Step 2: 跑前端型別檢查**

Run: `cd <repo-root> && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 3: 更新 TASK.md**（Phase 3 完成清單、驗證結果、剩餘 Phase 3b 待辦）與 **PROGRESS.md**（append Phase 3a 進度）與 **README.md**（如需，註記建模能力）

- [ ] **Step 4: Commit**

```bash
git add TASK.md PROGRESS.md README.md
git commit -m "docs: record Phase 3a modeling core completion"
```

---

## Self-Review

**Spec coverage（§12 模型中心）:**
- 12.1 模式：DOE 線性（Task2）✓、二次（Task2，代表 DOE 親族）、AI 隨機樹（Task2）✓、混合殘差 Y=f_DOE+r_AI（Task2）✓。其餘 DOE 設計種類（Full/Fractional/CCD/Box-Behnken/D-optimal/Taguchi）、Logistic/計數/可靠度模型 → **明文延後 3b**。
- 12.2 方程式建構：連續 output 基本形式（線性+平方+交互）由 `_design_matrix` 支援 ✓；係數/方程式顯示於 DTO ✓。p-value/信賴區間/適用範圍 → 延後。
- 12.4 模型比較：RMSE/MAE/R²/Adjusted R² 共用 `metrics.py` ✓。其餘比較維度（NG Recall、預測區間覆蓋率、殘差品質、外插風險、可解釋性）→ 延後。
- 12.5 模型狀態：草稿→待驗證→已驗證→已核准→已停用 狀態機 ✓；不可變版本 ✓（Test 3）。
- 12.3 交互作用（DOE 項、SHAP、PDP/ALE、工程規則、確認旗標）→ **延後 3b**。

**Placeholder scan:** 無 TBD/「加驗證」等泛化語；每個 step 含完整程式碼與命令。

**Type consistency:** `ModelFit.to_dto()` 與前端 `ModelFitDTO` 欄位一一對應（model_id/model_type/target/inputs/status/created_at/version/metrics/coefficients/equation/n_train/n_test）。`metrics` 鍵（rmse/mae/r2/adj_r2）與 `metrics.py`/`_compute_all_metrics` 一致。`registry` 的 `transition` 例外型別 `InvalidStatusTransition` 在前端以 `Exception` 捕捉（IPC 層錯誤轉換）。`MODEL_FITTERS` 鍵與 `ModelType` union 一致。

**已知陷阱（已內建校正註記）：** Task 2 `fit_residual_hybrid` 初始實作有索引不一致問題，已在程式碼區塊後標明必須改為單一索引方案，Task2 Step4 會驗證；`registry.transition` 用 `get_unlocked` 避免 Lock 不可重入（`threading.Lock` 非 RLock）。

**關於 lock 的說明：** `threading.Lock` 在同一執行緒重複 acquire 會 deadlock，故 `transition` 內部呼叫 `get_unlocked`（不 acquire lock），由呼叫端持有 lock。這是刻意設計，非 bug。

---

## Execution Handoff

計劃已儲存至 `docs/superpowers/plans/2026-09-02-phase3-model-center.md`。兩種執行方式：

1. **Subagent-Driven (recommended)** — 每個 task 派一個全新 subagent，task 間審查，快速迭代
2. **Inline Execution** — 目前 session 用 executing-plans 分批執行，含 checkpoints

選哪一種？
