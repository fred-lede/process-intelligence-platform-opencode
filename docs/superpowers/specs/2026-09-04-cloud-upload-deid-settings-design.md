# Cloud Upload 去識別化設定改進設計（spec 11A, 24）

日期：2026-09-04
狀態：設計（待實作）
範圍：改進既有「Settings → Cloud Upload」卡片，使其支援實際資料集選擇與手動欄位遮蔽設定。

## 背景與現況

系統已有 Cloud Upload 去識別化功能：

- **Backend**（`engine/src/process_intelligence_engine/data/deidentify.py`）：
  - `generate_preview` 依欄位名稱 pattern 自動偵測敏感欄位（barcode/serial/operator/name/email/phone/address/part_number/sku 等），
    字串欄 → `hash` 截短，數值欄 → 置為 `"MASKED"`；可對數值欄加入 Gaussian 雜訊（`noise_std`）。
  - `apply_masking` 產出實際上傳 DataFrame；`record_upload` / `list_records` 維護審計歷史。
- **IPC**（`main.py`）：`cloud/preview`、`cloud/upload`、`cloud/records` 均已 wiring。
  `_handle_cloud_preview` / `_handle_cloud_upload` 已接受 `dataset_id`、`sensitive_columns`、`excluded_columns`、`noise_std`、`seed`。
- **Frontend**（`src/features/settings/Settings.tsx`「Cloud Upload 卡片」）：
  - 目前 **hardcode `demo_dataset`**，無法選已匯入資料集，也無法手動標記敏感/排除欄位或選擇遮蔽策略。

## 目標

在保留現有流程（Preview → Confirmation Modal → 審計歷史）前提下：

1. **資料集選擇**：從已匯入資料集（`data/datasets` registry，即 `getDataAssets()`）下拉選擇要上傳的資料集，取代 hardcode `demo_dataset`。
2. **手動欄位設定**：對所選資料集的所有欄位，逐欄標記分類（傳送/遮蔽/排除），並為遮蔽欄位選擇遮蔽策略。
3. **遮蔽策略**：每一遮蔽欄位可選 `hash` / `masked` / `noise`（`noise` 僅適用於數值欄）。
4. **審計歷史保留**：`cloud/records` 歷史表不變。

## Architecture / 資料流

```
Settings 卡片
  │  載入 getDataAssets() → 資料集下拉
  │  選定資料集 → 載入欄位清單（REGISTRY 欄位可從 preview 回傳 total_columns 推導，或另取）
  │  逐欄設定分類與策略 → 組 params
  ▼
previewCloudUpload { dataset_id, sensitive_columns, excluded_columns, strategy_overrides, noise_std, seed }
  │  backend: cloud/preview → generate_preview(...) → UploadPreview.to_dict()
  ▼
顯示 preview（transmitted/masked/excluded + mask_strategies + noise_config + upload_hash）
  │
confirmCloudUpload { ... + operator/provider/model_version/purpose }
  │  backend: cloud/upload → record_upload(...)
  ▼
審計歷史（cloud/records）
```

## Backend 變更

### 1. `deidentify.py` — `generate_preview` 增加 `strategy_overrides`

簽章新增 `strategy_overrides: dict[str, str] | None = None`，並在 `apply_masking` 同樣支援。

- `strategy_overrides`：`{ column: "hash" | "masked" | "noise" }`。
- 遮蔽欄位的策略解析順序：
  1. 若 `column in strategy_overrides` → 用指定策略；
  2. 否則沿用現有 dtype 自動判定（object→hash、數值→masked）。
- 對「傳送」欄位，`strategy_overrides` 中標為 `noise` 者加入 `noise_config`（與現有 `noise_std` 行為一致，僅適用數值欄）。
- 若 `noise` 指定在非數值欄 → 忽略，保留自動/預設行為並可加入 warning。
- 新增/調整 `UploadPreview`（若有需要）以回傳最終採用的 `mask_strategies`（已含 override 結果）。

`apply_masking` 增加同參數，使實際上傳資料與 preview 一致。

### 2. `main.py` — 透傳 `strategy_overrides`

`_handle_cloud_preview` / `_handle_cloud_upload` 讀取 `params.get("strategy_overrides", {})` 並傳入 `generate_upload_preview`。

## Frontend 變更（Settings 卡片）

### 資料集下拉
- 掛載時載入 `getDataAssets()`，`Select` 列出 `datasets[].dataset_id`（顯示 source_file）。
- 未選資料集 → Preview/Confirm 禁用、顯示提示。
- 選定後取得該資料集欄位清單：呼叫既有 `detectFields(columns, dataset_id)`（`data/detect_fields`，main.py:328 在 `dataset_id` 存在時回傳每欄 `name`/`data_type`/`role`）。以此建欄位表格並判斷 `noise` 策略是否有效（依 `data_type` 是否數值）。

### 欄位設定表格（每欄一列）
- 分類：傳送 / 遮蔽 / 排除（Radio 或下拉）。
- 遮蔽策略（僅「遮蔽」列啟用）：Hash / MASKED / 雜訊（`noise` 僅數值欄可用）。
- `sensitive_columns` = 標為「遮蔽」的欄位；`excluded_columns` = 標為「排除」的欄位；
  `strategy_overrides` = 遮蔽欄位（及其 `noise` 選項，若標為傳送但策略為 noise 也納入）。

### 流程
- Preview：呼叫 `previewCloudUpload(...)`（含 `strategy_overrides`）。
- Confirm Modal：沿用現有內容，額外顯示最終 `mask_strategies`。
- 審計歷史表保留。

### engine.ts
- `CloudPreviewParams` / `CloudUploadParams` 已含 `sensitive_columns`/`excluded_columns`，補 `strategy_overrides?: Record<string, string>`。

### i18n（en / zh-TW / es-MX）
- `cloud` section 新增 keys：資料集選擇（label/placeholder）、欄位表格欄頭（欄位/分類/策略）、策略名稱（hash/masked/noise）、無資料集提示、策略-noise-非數值警告 等。

## 測試

- **Backend**（`engine/tests/`）：
  - `generate_preview` 的 `strategy_overrides`：hash/masked/noise 覆寫自動判定。
  - `apply_masking` 產出與 preview 一致。
  - `noise` 於非數值欄被忽略。
  - IPC `cloud/preview` / `cloud/upload` 透傳 `strategy_overrides`。
- **前端**：`npx tsc --noEmit`、`npm run build` clean；三語 JSON 有效。

## 非目標（YAGNI）
- 不新增獨立 Cloud Upload Tab。
- 不做 per-column 獨立 `noise_std`（沿用單一全局 `noise_std`）。
- 不實作真正的第三方雲端送出——僅維護「去識別化後待上傳」的預覽/審計紀錄（與現況一致）。

## 欄位清單取得方式（已確認）

資料集選擇後，用既有 `data/detect_fields`（`detectFields(columns, dataset_id)`）取得該資料集全欄位及其 `name`/`data_type`，作為欄位設定表格的輸入來源。無需新增 IPC。
