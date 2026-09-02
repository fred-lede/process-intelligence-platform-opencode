# Phase 8 — SPC 統計製程控制：設計規格

## 1. 概述

在現有資料管道（data import → field detection → quality check → spec define）之上，新增 SPC 統計製程控制功能。使用者可以選擇既有資料或手動輸入，檢視 I-MR、X-bar/R、X-bar/S 控制圖，並計算製程能力指數。

## 2. 支援圖表

### 連續值圖表
| 圖表 | 適用場景 | 中心線 | UCL/LCL |
|------|---------|--------|---------|
| I-MR | 單值（n=1）| X̄ | X̄±3σ̂ (I), D4·R̄ / D3·R̄ (MR) |
| X-bar + R | 子群組 n=2~9 | X̄̄ | X̄̄±A2·R̄ / D4·R̄ / D3·R̄ |
| X-bar + S | 子群組 n≥2 | X̄̄ | X̄̄±A3·s̄ / B4·s̄ / B3·s̄ |

### 計數型圖表（後期）
| 圖表 | 適用場景 |
|------|---------|
| p 圖 | 不良比例（子群組大小可變） |
| np 圖 | 不良數（子群組大小固定） |
| c 圖 | 缺陷數（固定檢查單位） |
| u 圖 | 平均每單位缺陷數 |

### 製程能力指數
| 指標 | 公式 | 解讀 |
|------|------|------|
| Cp | (USL - LSL) / (6σ) | 潛在能力（不考慮偏離） |
| Cpk | min((USL-μ)/3σ, (μ-LSL)/3σ) | 實際能力 |
| Pp | (USL - LSL) / (6σ_overall) | 整體變異 |
| Ppk | min((USL-μ)/3σ_overall, (μ-LSL)/3σ_overall) | 整體實際能力 |

## 3. Western Electric 規則

| 規則 | 條件 | 意義 |
|------|------|------|
| 1 | 1點超出 3σ | 異常訊號 |
| 2 | 2/3點超出 2σ（同側） | 趨勢訊號 |
| 3 | 4/5點超出 1σ（同側） | 偏移訊號 |
| 4 | 8點連續在中心線同側 | 均值偏移 |
| 5 | 6點連續上升或下降 | 趨勢 |
| 6 | 15點連續在 ±1σ 內 | 變異過小（雙層分布） |
| 7 | 14點上下交錯 | 系統性變異 |

## 4. 資料來源

### 既有資料模式
- 讀取專案 data pipeline 中已確認的 output 欄位
- 若資料有 batch/timestamp 欄位，提供「按欄位分組」選項
- 否則使用固定子群組大小（預設 5）

### 手動輸入模式
- 逐筆輸入數值（每行一個值）
- 或輸入子群組格式（每行一個子群組，逗號分隔）
- 支援即時監控場景（少量即時資料）

### 欄位設定
- 輸出欄位（output field）：從 project spec 中自動帶入
- 子群組大小：輸入框（預設 5）
- 分組欄位：下拉選單（若現有資料有 batch/datetime 欄位）
- 控制限設定：auto（3σ）或手動

## 5. 系統架構

```
src/features/spc/SPC.tsx          — 前端 UI
src/lib/engine.ts                  — SPC API 封裝
engine/src/process_intelligence_engine/spc.py  — 計算引擎
engine/src/process_intelligence_engine/main.py — IPC handlers
```

### IPC handlers
- `spc/analyze` — 計算控制圖數據（含 WE 規則）
- `spc/capability` — 計算製程能力指數

### 前端 API
```typescript
analyzeSPC(params: {
  dataset_id?: string
  column: string
  subgroup_size?: number
  group_column?: string
  control_limits?: { lsl?: number; usl?: number }
  source: 'existing' | 'manual'
  manual_values?: number[]
}): Promise<SPCAnalysisResult>

getCapability(params: {
  dataset_id?: string
  column: string
  lsl?: number
  usl?: number
  source: 'existing' | 'manual'
  manual_values?: number[]
}): Promise<CapabilityResult>
```

### SPC 計算結果結構
```python
@dataclass
class SPCResult:
    chart_type: str          # "i-mr" | "xbar-r" | "xbar-s"
    x_values: list[float]    # 個別值
    control_limits: dict     # {"center": float, "ucl": float, "lcl": float}
    mr_values: list[float]   # 移動範圍（I-MR only）
    subgroup_stats: dict     # 子群組統計（X-bar/R/S only）
    violations: list[dict]   # {rule: int, point_idx: int, description: str}
    capability: CapabilityResult | None

@dataclass
class CapabilityResult:
    cp: float
    cpk: float
    pp: float
    ppk: float
    sigma_estimate: str      # "within" | "overall"
    n_subgroups: int
    total_observations: int
```

## 6. UI 設計

### 頁面佈局
```
┌─────────────────────────────────────────────────┐
│ SPC 統計製程控制                                  │
├─────────────────────────────────────────────────┤
│ [資料來源: ●既有資料 ○手動輸入]                    │
│ [輸出欄位: ______ ▼]  [子群組大小: ___]           │
│ [分組欄位: ______ ▼]  [計算]                      │
├─────────────────────────────────────────────────┤
│ 製程能力 (Cp: __ Cpk: __ Pp: __ Ppk: __)         │
│ [Cp/Cpk  ≥ 1.33 綠色 / 1.0~1.33 黃色 / <1.0 紅色] │
├─────────────────────────────────────────────────┤
│ 控制圖                                           │
│  [圖表類型: ●I-MR ○X-bar+R ○X-bar+S]            │
│  [Plotly 圖表]                                    │
│  - 個別值/平均值線                                │
│  - 中心線 (CL)                                    │
│  - UCL/LCL 虛線                                  │
│  - ±1σ, ±2σ 虛線                                 │
│  - 違規點標紅                                     │
├─────────────────────────────────────────────────┤
│ Western Electric 規則違規清單                     │
│ [表格: 規則 | 點位置 | 描述]                      │
└─────────────────────────────────────────────────┘
```

### 控制圖顏色
- 中心線 (CL)：綠色虛線
- UCL/LCL：橙色虛線
- ±1σ：淺黃色虛線
- ±2σ：淺橙色虛線
- 正常點：藍色
- 違規點：紅色

## 7. 實作步驟

### Phase 8a — 後端引擎
1. `spc.py` — 控制圖計算（I-MR, X-bar/R, X-bar/S）
2. `spc.py` — 製程能力指數計算
3. `spc.py` — Western Electric 規則檢測
4. `main.py` — `spc/analyze`, `spc/capability` IPC handlers
5. `test_spc.py` — 單元測試

### Phase 8b — 前端
6. `engine.ts` — SPC API 封裝
7. `SPC.tsx` — 控制圖 UI + 能力指數卡片
8. `Sidebar.tsx` + `App.tsx` — 導航整合
9. i18n en/zh-TW

## 8. 依賴

- 既有資料管道（data import, field detection, quality check）
- Plotly.js（控制圖繪製，已用於 Exploration 頁面）
- 專案 spec（output field + LSL/USL）

## 9. 不納入範圍（後續 Phase）

- 計數型圖（p/np/c/u）— 需要計數資料結構
- 即時資料串流 — 需要額外後端
- 自動警報 — 需要通知系統
- 歷史資料比較 — 需要資料儲存
