# Cloud Upload 去識別化設定改進 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 Settings → Cloud Upload 卡片可選擇真實已匯入資料集、逐欄標記傳送/遮蔽/排除、並為遮蔽欄位選擇遮蔽策略（hash / masked / noise）。

**Architecture:** Backend `deidentify.py` 的 `generate_preview`/`apply_masking` 增加 `strategy_overrides` 參數（per-column 覆寫自動遮蔽策略），並經 `main.py` 的 `cloud/preview`/`cloud/upload` IPC 透傳。Frontend Settings 卡片以 `getDataAssets()` 填資料集下拉、以 `detectFields(columns, dataset_id)` 取得欄位清單與 dtype、逐欄設定分類與策略，再組 params 呼叫既有 IPC。

**Tech Stack:** Python 3.11 + pandas（engine）、Tauri 2.0 + React 18 + TypeScript + AntD 5（frontend）、i18next（en/zh-TW/es-MX）。

---

## 檔案結構

- `engine/src/process_intelligence_engine/data/deidentify.py` — 改 `generate_preview`/`apply_masking`（加 `strategy_overrides`）
- `engine/src/process_intelligence_engine/main.py` — `_handle_cloud_preview`/`_handle_cloud_upload` 透傳 `strategy_overrides`
- `engine/tests/test_deidentify.py` — **新增**，策略覆寫的單元測試
- `engine/tests/test_main_handlers.py` — 加 `cloud/preview`/`cloud/upload` 透傳測試
- `src/lib/engine.ts` — `CloudPreviewParams`/`CloudUploadParams` 加 `strategy_overrides`
- `src/features/settings/Settings.tsx` — 資料集下拉 + 欄位設定表格 + 整合
- `src/i18n/en.json` / `zh-TW.json` / `es-MX.json` — cloud keys 擴充

---

### Task 1: Backend — `generate_preview` 支援 `strategy_overrides`

**Files:**
- Modify: `engine/src/process_intelligence_engine/data/deidentify.py:105-194`（`generate_preview`）
- Test: `engine/tests/test_deidentify.py`（**新增**）

- [ ] **Step 1: 寫失敗測試**

```python
"""Tests for cloud upload de-identification strategy overrides."""
import pandas as pd

from process_intelligence_engine.data.deidentify import (
    _DEID_ENGINE as deid,
    apply_deidentification,
)


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "temperature": [230.5, 241.0, 255.2],
            "operator": ["Alice", "Bob", "Carol"],
            "ok_flag": ["OK", "NG", "OK"],
        }
    )


def test_strategy_overrides_mask_with_hash():
    df = _sample_df()
    preview = deid.generate_preview(
        df,
        "ds1",
        sensitive_columns=["operator"],
        strategy_overrides={"operator": "hash"},
    )
    assert preview.mask_strategies["operator"] == "hash"
    out = apply_deidentification(df, preview)
    assert set(out["operator"].unique()) == {"MASKED"}
    assert out["operator"].iloc[0] == "MASKED"


def test_strategy_overrides_mask_with_masked():
    df = _sample_df()
    preview = deid.generate_preview(
        df,
        "ds1",
        sensitive_columns=["temperature"],
        strategy_overrides={"temperature": "masked"},
    )
    assert preview.mask_strategies["temperature"] == "masked"
    out = apply_deidentification(df, preview)
    assert (out["temperature"] == "MASKED").all()


def test_strategy_overrides_noise_on_numeric_transmitted():
    df = _sample_df()
    preview = deid.generate_preview(
        df,
        "ds1",
        strategy_overrides={"temperature": "noise"},
        noise_std=0.5,
    )
    assert preview.noise_config["temperature"]["method"] == "gaussian"
    assert preview.noise_config["temperature"]["std"] == 0.5
    out = apply_deidentification(df, preview, seed=7)
    assert pd.api.types.is_float_dtype(out["temperature"])


def test_noise_on_non_numeric_is_ignored():
    df = _sample_df()
    preview = deid.generate_preview(
        df,
        "ds1",
        sensitive_columns=["operator"],
        strategy_overrides={"operator": "noise"},
    )
    # non-numeric sensitive cannot use noise -> stays auto (hash) and not in noise_config
    assert preview.mask_strategies["operator"] == "hash"
    assert "operator" not in preview.noise_config
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd engine && .venv/bin/python -m pytest tests/test_deidentify.py -q`
Expected: `TypeError: generate_preview() got an unexpected keyword argument 'strategy_overrides'`

- [ ] **Step 3: 實作**

在 `deidentify.py` 的 `generate_preview` 簽章加 `strategy_overrides: dict[str, str] | None = None`，並在遮蔽策略判定後套用：

```python
    def generate_preview(
        self,
        df: pd.DataFrame,
        dataset_id: str,
        sensitive_columns: list[str] | None = None,
        excluded_columns: list[str] | None = None,
        strategy_overrides: dict[str, str] | None = None,
        noise_std: float = 0.0,
        seed: int = 42,
    ) -> UploadPreview:
        ...
        overrides = strategy_overrides or {}

        # Build mask strategies
        mask_strategies: dict[str, str] = {}
        for col in masked:
            if overrides.get(col) == "hash":
                mask_strategies[col] = "hash"
            elif overrides.get(col) == "masked":
                mask_strategies[col] = "masked"
            elif overrides.get(col) == "noise" and pd.api.types.is_numeric_dtype(df[col]):
                mask_strategies[col] = "noise"
            elif df[col].dtype in ("object", "string", "category"):
                mask_strategies[col] = "hash"
            else:
                mask_strategies[col] = "replace"

        # Build noise config
        noise_config: dict[str, dict] = {}
        rng = np.random.default_rng(seed)
        for col in transmitted:
            if overrides.get(col) == "noise" and pd.api.types.is_numeric_dtype(df[col]):
                noise_config[col] = {"std": noise_std, "method": "gaussian"}
            elif pd.api.types.is_numeric_dtype(df[col]) and noise_std > 0:
                noise_config[col] = {"std": noise_std, "method": "gaussian"}
```

> 注意：`mask_strategies` 值現在可能為 `"noise"`（數值遮蔽 + 雜訊）。`noise_config` 在底下第 217 行只掃 `transmitted`，需一併涵蓋 masked 且策略為 noise 的數值欄。調整 `apply_masking`（Task 2）以正確套用。

- [ ] **Step 4: 跑測試確認通過**

Run: `cd engine && .venv/bin/python -m pytest tests/test_deidentify.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/data/deidentify.py engine/tests/test_deidentify.py
git commit -m "feat(copula-deid): add strategy_overrides to de-identification preview"
```

> Note：commit message 前綴用 `feat(cloud)` 亦可；此處沿用現況慣例，若你偏好 `feat(cloud)` 可自行調整前綴。

---

### Task 2: Backend — `apply_masking` 依策略正確遮蔽並加雜訊

**Files:**
- Modify: `engine/src/process_intelligence_engine/data/deidentify.py:196-221`（`apply_masking`）
- Test: `engine/tests/test_deidentify.py`

- [ ] **Step 1: 寫失敗測試（noise 遮蔽欄位應加上雜訊）**

```python
def test_noise_masked_column_gets_noise():
    df = _sample_df()
    preview = deid.generate_preview(
        df,
        "ds1",
        sensitive_columns=["temperature"],
        strategy_overrides={"temperature": "noise"},
        noise_std=0.5,
    )
    out = apply_deidentification(df, preview, seed=3)
    # column present, numeric, and differs from original (noise applied)
    assert "temperature" in out.columns
    assert pd.api.types.is_float_dtype(out["temperature"])
    assert (out["temperature"] != df["temperature"]).any()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd engine && .venv/bin/python -m pytest tests/test_deidentify.py::test_noise_masked_column_gets_noise -q`
Expected: FAIL（noise_config 未涵蓋 masked 欄位 → temperature 被置為 "MASKED" 或未被遮蔽）

- [ ] **Step 3: 實作** — 在 `apply_masking` 中，遮蔽欄位改以 `preview.mask_strategies` 判定，而非固定 hash/replace：

```python
    def apply_masking(
        self,
        df: pd.DataFrame,
        preview: UploadPreview,
        seed: int = 42,
    ) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        df_out = df[preview.transmitted_columns + list(preview.masked_columns)].copy()

        # Hash / mask / leave-for-noise sensitive columns
        for col in preview.masked_columns:
            if preview.mask_strategies.get(col) == "hash":
                df_out[col] = df_out[col].apply(
                    lambda x: sha256(str(x).encode()).hexdigest()[:8] if pd.notna(x) else "NULL"
                )
            elif preview.mask_strategies.get(col) == "masked":
                df_out[col] = "MASKED"
            # strategy "noise" leaves warm; noise applied below

        # Add noise to numeric columns (transmitted or noise-masked)
        for col, cfg in preview.noise_config.items():
            if col in df_out.columns and cfg["method"] == "gaussian":
                noise = rng.normal(0, cfg["std"], len(df_out))
                df_out[col] = df_out[col].astype(float) + noise

        return df_out
```

> 重要：`generate_preview` 中 `noise_config` 現在也涵蓋 masked-noise 欄（Task 1「注意」），且 hash 改用 `apply` 逐行——`apply_masking` 的 `df_out` 需同時含 `transmitted_columns + masked_columns`，否則 noise-masked 欄位會消失。上方程式即涵蓋此點。

- [ ] **Step 4: 跑全部 deid 測試確認通過**

Run: `cd engine && .venv/bin/python -m pytest tests/test_deidentify.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/data/deidentify.py engine/tests/test_deidentify.py
git commit -m "feat(deid): apply per-column noise masking in de-identification output"
```

---

### Task 3: Backend IPC — `cloud/preview` / `cloud/upload` 透傳 `strategy_overrides`

**Files:**
- Modify: `engine/src/process_intelligence_engine/main.py:1571-1611`（`_handle_cloud_preview`/`_handle_cloud_upload`）
- Test: `engine/tests/test_main_handlers.py`

- [ ] **Step 1: 寫失敗測試**

```python
def test_handle_cloud_preview_passes_strategy_overrides(tmp_path):
    csv_text = "\n".join(
        ["temperature,operator,ok_flag", "230.5,Alice,OK", "241.0,Bob,NG", "255.2,Carol,OK"]
    )
    dataset_id = _import_csv_and_return_id(tmp_path, csv_text)

    result = handle_request(
        "cloud/preview",
        {
            "dataset_id": dataset_id,
            "sensitive_columns": ["temperature"],
            "strategy_overrides": {"temperature": "noise"},
            "noise_std": 0.5,
        },
    )
    assert result["noise_config"]["temperature"]["method"] == "gaussian"
    assert result["noise_config"]["temperature"]["std"] == 0.5


def test_handle_cloud_preview_and_upload_consistent(tmp_path):
    csv_text = "\n".join(
        ["temperature,operator,ok_flag", "230.5,Alice,OK", "241.0,Bob,NG", "255.2,Carol,OK"]
    )
    dataset_id = _import_csv_and_return_id(tmp_path, csv_text)

    preview = handle_request(
        "cloud/preview",
        {
            "dataset_id": dataset_id,
            "sensitive_columns": ["operator"],
            "strategy_overrides": {"operator": "hash"},
        },
    )
    assert preview["mask_strategies"]["operator"] == "hash"

    result = handle_request(
        "cloud/upload",
        {
            "dataset_id": dataset_id,
            "sensitive_columns": ["operator"],
            "strategy_overrides": {"operator": "hash"},
            "operator": "qa",
            "provider": "azure",
            "model_version": "gpt-5",
            "purpose": "training",
        },
    )
    assert result["record_id"]
    assert result["columns_uploaded"]  # non-empty
    assert "operator" in result["masked_columns"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd engine && .venv/bin/python -m pytest tests/test_main_handlers.py::test_handle_cloud_preview_passes_strategy_overrides tests/test_main_handlers.py::test_handle_cloud_preview_and_upload_consistent -q`
Expected: FAIL（`strategy_overrides` 未被傳入 `generate_preview`）

- [ ] **Step 3: 實作** — 兩個 handler 讀取並透傳：

```python
def _handle_cloud_preview(params: dict) -> dict:
    dataset_id = params["dataset_id"]
    df = REGISTRY.get(dataset_id)
    sensitive_columns = params.get("sensitive_columns", [])
    excluded_columns = params.get("excluded_columns", [])
    strategy_overrides = params.get("strategy_overrides", {})
    noise_std = float(params.get("noise_std", 0.0))
    seed = int(params.get("seed", 42))

    preview = generate_upload_preview(
        df, dataset_id, sensitive_columns, excluded_columns,
        strategy_overrides, noise_std, seed,
    )
    return _plain_types(preview.to_dict())
```

`_handle_cloud_upload` 同法加 `strategy_overrides = params.get("strategy_overrides", {})` 並傳入 `generate_upload_preview(df, dataset_id, sensitive_columns, excluded_columns, strategy_overrides, noise_std, seed)`。其餘（operator/provider/model_version/purpose、`record_upload`）不變。

> 檢查 `generate_upload_preview`（deidentify.py:271-282）位置式參數順序：`(df, dataset_id, sensitive_columns, excluded_columns, noise_std, seed)`。插入 `strategy_overrides` 後順序變為 `(df, dataset_id, sensitive_columns, excluded_columns, strategy_overrides, noise_std, seed)` —— 需一併更新該 wrapper 與其呼叫。

- [ ] **Step 4: 更新 wrapper（若 Step 3 出現 TypeError）**

在 `deidentify.py:271` 更新 `generate_upload_preview` 簽章與轉傳。若沿用位置式呼叫，直接改：

```python
def generate_upload_preview(
    df: pd.DataFrame,
    dataset_id: str,
    sensitive_columns: list[str] | None = None,
    excluded_columns: list[str] | None = None,
    strategy_overrides: dict[str, str] | None = None,
    noise_std: float = 0.0,
    seed: int = 42,
) -> UploadPreview:
    return _DEID_ENGINE.generate_preview(
        df, dataset_id, sensitive_columns, excluded_columns,
        strategy_overrides, noise_std, seed,
    )
```

Run: `cd engine && .venv/bin/python -m pytest tests/test_main_handlers.py -q`
Expected: 所有既有 + 2 新增全通過

- [ ] **Step 5: 跑全引擎測試**

Run: `cd engine && .venv/bin/python -m pytest tests/ -q`
Expected: 既有基線（task 前 275 passed, 1 skipped）+ 新增測試通過（約 279 passed）

- [ ] **Step 6: Commit**

```bash
git add engine/src/process_intelligence_engine/data/deidentify.py engine/src/process_intelligence_engine/main.py engine/tests/test_main_handlers.py
git commit -m "feat(cloud): pass strategy_overrides through cloud preview/upload IPC"
```

---

### Task 4: Frontend types — `engine.ts` 加 `strategy_overrides`

**Files:**
- Modify: `src/lib/engine.ts:1087-1114`（`CloudPreviewParams`/`CloudUploadParams`）

- [ ] **Step 1: 改型別** — 兩個 interface 各加一欄：

```typescript
export interface CloudPreviewParams {
  dataset_id: string
  sensitive_columns?: string[]
  excluded_columns?: string[]
  strategy_overrides?: Record<string, string>
  noise_std?: number
  seed?: number
}

export interface CloudUploadParams {
  dataset_id: string
  sensitive_columns?: string[]
  excluded_columns?: string[]
  strategy_overrides?: Record<string, string>
  noise_std?: number
  seed?: number
  operator: string
  provider: string
  model_version: string
  purpose: string
}
```

- [ ] **Step 2: 驗證**

Run: `npx tsc --noEmit`
Expected: 無 error

- [ ] **Step 3: Commit**

```bash
git add src/lib/engine.ts
git commit -m "feat(cloud): add strategy_overrides to cloud params types"
```

---

### Task 5: Frontend UI — Settings 卡片：資料集選擇 + 欄位設定表格

**Files:**
- Modify: `src/features/settings/Settings.tsx`
- Modify: `src/i18n/en.json` / `zh-TW.json` / `es-MX.json`

- [ ] **Step 1: 加 imports 與 state**

在 `Settings.tsx`：

```tsx
import { getDataAssets, detectFields, type DataAsset, type DetectedField } from '../../lib/engine'
```

新增 state（在既有 cloud state 附近）：

```tsx
const [cloudDatasets, setCloudDatasets] = useState<DataAsset[]>([])
const [cloudDatasetId, setCloudDatasetId] = useState<string>('')
const [cloudFields, setCloudFields] = useState<DetectedField[]>([])
const [cloudLoadingFields, setCloudLoadingFields] = useState(false)
const [cloudColClass, setCloudColClass] = useState<Record<string, 'transmit' | 'mask' | 'exclude'>>({})
const [cloudColStrategy, setCloudColStrategy] = useState<Record<string, 'hash' | 'masked' | 'noise'>>({})
```

- [ ] **Step 2: 載入資料集 + 選取後載入欄位**

在現有 `loadData()`（或 cloud 區塊的 useEffect）加入載入資料集；新增載入欄位 handler：

```tsx
useEffect(() => {
  getDataAssets()
    .then(res => setCloudDatasets(res.datasets))
    .catch(() => {})
}, [])

const loadCloudFields = async (datasetId: string) => {
  if (!datasetId) return
  setCloudLoadingFields(true)
  try {
    const res = await detectFields([], datasetId)
    const fields = res.fields
    setCloudFields(fields)
    // 預設：偵測為 sensitive 的欄位標 mask(hash)，其餘 transmit
    const cls: Record<string, 'transmit' | 'mask' | 'exclude'> = {}
    const strat: Record<string, 'hash' | 'masked' | 'noise'> = {}
    for (const f of fields) {
      const isSensitive = f.role === 'sensitive' || f.role === 'identifier'
      cls[f.name] = isSensitive ? 'mask' : 'transmit'
      strat[f.name] = isSensitive ? 'hash' : 'masked'
    }
    setCloudColClass(cls)
    setCloudColStrategy(strat)
  } catch {
    // engine unavailable
  } finally {
    setCloudLoadingFields(false)
  }
}
```

- [ ] **Step 3: 加 i18n keys**（三語各加，此處列 en）

`en.json` 的 `cloud` section 新增：

```json
"dataset": "Dataset",
"selectDataset": "Select dataset to upload",
"field": "Field",
"classification": "Classification",
"strategy": "Masking Strategy",
"transmit": "Transmit",
"mask": "Mask",
"exclude": "Exclude",
"strategyHash": "Hash",
"strategyMasked": "MASKED value",
"strategyNoise": "Gaussian noise",
"noDataset": "Select a dataset to configure columns",
"noiseNonNumericWarn": "Noise strategy only applies to numeric columns"
```

`zh-TW.json`：
```json
"dataset": "資料集",
"selectDataset": "選擇要上傳的資料集",
"field": "欄位",
"classification": "分類",
"strategy": "遮蔽策略",
"transmit": "傳送",
"mask": "遮蔽",
"exclude": "排除",
"strategyHash": "雜湊",
"strategyMasked": "遮罩值",
"strategyNoise": "高斯雜訊",
"noDataset": "請先選擇資料集以設定欄位",
"noiseNonNumericWarn": "雜訊策略僅適用於數值欄位"
```

`es-MX.json`：
```json
"dataset": "Conjunto de datos",
"selectDataset": "Selecciona el conjunto de datos a subir",
"field": "Campo",
"classification": "Clasificación",
"strategy": "Estrategia de enmascarado",
"transmit": "Transmitir",
"mask": "Enmascarar",
"exclude": "Excluir",
"strategyHash": "Hash",
"strategyMasked": "Valor MASKED",
"strategyNoise": "Ruido gaussiano",
"noDataset": "Selecciona un conjunto de datos para configurar los campos",
"noiseNonNumericWarn": "La estrategia de ruido solo aplica a campos numéricos"
```

- [ ] **Step 4: 改 Cloud Upload 卡片的 UI**

將資料集選擇與欄位表格放在 `Preview` 按鈕之前的 `Space direction="vertical"` 中：

```tsx
<Select
  placeholder={t('cloud.selectDataset')}
  value={cloudDatasetId || undefined}
  onChange={id => { setCloudDatasetId(id); setCloudPreview(null); loadCloudFields(id) }}
  style={{ width: 280 }}
  loading={cloudLoadingFields}
  options={cloudDatasets.map(d => ({ value: d.dataset_id, label: `${d.source_file} (${d.dataset_id})` }))}
/>

{cloudDatasetId ? (
  <Table
    size="small"
    rowKey="name"
    loading={cloudLoadingFields}
    dataSource={cloudFields}
    pagination={false}
    scroll={{ x: 480 }}
    columns={[
      { title: t('cloud.field'), dataIndex: 'name', width: 160 },
      { title: t('cloud.dataType'), dataIndex: 'data_type', width: 90 },
      {
        title: t('cloud.classification'),
        render: (_, r) => (
          <Select
            value={cloudColClass[r.name] ?? 'transmit'}
            onChange={v => setCloudColClass(prev => ({ ...prev, [r.name]: v }))}
            options={[
              { value: 'transmit', label: t('cloud.transmit') },
              { value: 'mask', label: t('cloud.mask') },
              { value: 'exclude', label: t('cloud.exclude') },
            ]}
            style={{ width: 120 }}
          />
        ),
      },
      {
        title: t('cloud.strategy'),
        render: (_, r) => {
          const isMasked = (cloudColClass[r.name] ?? 'transmit') === 'mask'
          const numeric = r.data_type !== 'category' && r.data_type !== 'string' && r.data_type !== 'text'
          return (
            <Select
              value={cloudColStrategy[r.name] ?? 'hash'}
              disabled={!isMasked}
              onChange={v => setCloudColStrategy(prev => ({ ...prev, [r.name]: v }))}
              options={[
                { value: 'hash', label: t('cloud.strategyHash') },
                { value: 'masked', label: t('cloud.strategyMasked') },
                { value: 'noise', label: t('cloud.strategyNoise'), disabled: !numeric },
              ]}
              style={{ width: 140 }}
            />
          )
        },
      },
    ]}
  />
) : (
  <Alert type="info" showIcon message={t('cloud.noDataset')} />
)}
```

> 注意 `data_type` 欄在 i18n 未定義——可在 cloud section 加 `"dataType": "Type"`（en）/ `"型別"`（zh-TW）/ `"Tipo"`（es-MX）。若 `DetectedField.data_type` 為字串值（如 "float"/"int"/"string"），依此判斷 numeric。

- [ ] **Step 5: Preview/Confirm 改用選取資料集與欄位設定**

將 `previewCloudUpload` 呼叫（現約 line 434）改為：

```tsx
const result = await previewCloudUpload({
  dataset_id: cloudDatasetId,
  sensitive_columns: Object.entries(cloudColClass).filter(([, c]) => c === 'mask').map(([n]) => n),
  excluded_columns: Object.entries(cloudColClass).filter(([, c]) => c === 'exclude').map(([n]) => n),
  strategy_overrides: Object.entries(cloudColClass)
    .filter(([, c]) => c === 'mask')
    .reduce<Record<string, string>>((acc, [n]) => {
      const s = cloudColStrategy[n] ?? 'hash'
      acc[n] = s === 'hidden' ? 'masked' : s
      return acc
    }, {}),
  noise_std: cloudNoiseStd,
})
setCloudPreview(result)
```

並在 Preview 按鈕加 `disabled={!cloudDatasetId}`、Confirm 的 `confirmCloudUpload` 同步加 same `dataset_id`/`sensitive_columns`/`excluded_columns`/`strategy_overrides`。

- [ ] **Step 6: 驗證**

Run: `npx tsc --noEmit && npm run build`
Expected: 兩者皆 clean，無 error

- [ ] **Step 7: 驗證三語 JSON 有效**

Run: `node -e "for (const l of ['en','zh-TW','es-MX']) { JSON.parse(require('fs').readFileSync('src/i18n/'+l+'.json','utf8')); console.log(l,'ok') }"`
Expected: 三行 ok

- [ ] **Step 8: Commit**

```bash
git add src/features/settings/Settings.tsx src/lib/engine.ts src/i18n/en.json src/i18n/zh-TW.json src/i18n/es-MX.json
git commit -m "feat(settings): dataset selection + per-column masking strategy for cloud upload"
```

---

### Task 6: 收尾 — 文件 + push

**Files:**
- Modify: `PROGRESS.md`、`TASK.md`

- [ ] **Step 1: 更新 PROGRESS.md / TASK.md**

在 Cloud Upload 既有進度後補一行：settings 卡片支援資料集選擇與 per-column 遮蔽策略（strategy_overrides），引用 spec 檔名。

- [ ] **Step 2: 全引擎測試 + build 最終驗證**

Run: `cd engine && .venv/bin/python -m pytest tests/ -q && cd .. && npx tsc --noEmit && npm run build`
Expected: 全 passed、tsc/build clean

- [ ] **Step 3: Commit + Push**

```bash
git add PROGRESS.md TASK.md
git commit -m "docs: record cloud upload de-id settings improvement"
git push origin main
```

---

## Self-Review

**Spec 覆蓋：**
- 資料集選擇 → Task 5（`getDataAssets` 下拉）
- 手動欄位設定（傳送/遮蔽/排除）→ Task 5 Step 4 表格分類欄
- 遮蔽策略（hash/masked/noise）→ Task 1/2（backend）+ Task 5（UI）
- 審計歷史保留 → 未改 `cloud/records` 與歷史表，Task 3 保留
- IPC 透傳 → Task 3、Task 4（型別）
- Test（backend unit + IPC）→ Task 1/2/3；tsc/build/三語驗證 → Task 5/6

**Placeholder 掃描：** 無 TBD/TODO；所有程式碼步驟皆有實際 code。

**型別一致性：** `strategy_overrides: Record<string,string>` 於 engine.ts、Settings.tsx、handler 三處一致（值 `hash`/`masked`/`noise`）。`generate_upload_preview` 參數順序在 Task 3 明示需配合更新，避免位置參數錯位。

**已知風險：** `apply_masking` 改為輸出 `transmitted + masked` 欄（Task 2），會讓被遮蔽欄位也出現在「實際上傳 DataFrame」中（值為 hash/"MASKED"/加噪）。這與現況（masked 欄不輸出）略有差異——但 cloud/upload 目前僅記錄審計而不真正送出，故不影響外部行為；preview 的 `masked_columns` 仍正確列出。
