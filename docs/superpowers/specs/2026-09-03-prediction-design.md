# Phase 10 — 互動預測 (What-if)：設計規格

## 1. 概述

工程師日常 What-if 工具：選擇已訓練的 DOE 模型，調整 input 參數，即時查看 predicted output 與 NG 判定。

## 2. 範圍

### 納入
- 從 Model Registry 選擇 DOE 模型（linear / quadratic）
- 每個 input 的滑桿 + 數值輸入（帶 min/max 範圍）
- 即時預測 output（使用 `predict_output` 邏輯）
- NG 判定（LSL/USL 比較）
- 模型方程式顯示
- 預設值還原（使用資料平均）

### 不納入（後續 Phase）
- Random Forest / Hybrid 模型
- 多模型比較
- 預測區間（置信區間）
- 情景保存/載入（持久化）

## 3. 架構

```
engine/src/process_intelligence_engine/prediction.py  — 預測引擎
main.py                     — IPC handlers (prediction/predict)
src/lib/engine.ts           — API 封裝
src/features/prediction/Prediction.tsx  — UI 組件
```

### IPC handlers
- `prediction/predict` — 給定 model_id + input_values → predicted output
- `prediction/model_info` — 取得模型的 input 範圍 + 方程式

## 4. UI 設計

```
┌─────────────────────────────────────────────────────────┐
│ 互動預測 (What-if)                                       │
├─────────────────────────────────────────────────────────┤
│ [模型選擇: ______ ▼]  [方程式: y = 10.0 + 2.0*x1...]    │
├─────────────────────────────────────────────────────────┤
│ Input 控制區                                            │
│  x1: [====●========]  100.0  (範圍: 80 ~ 120)          │
│  x2: [=====●======]   50.0   (範圍: 35 ~ 65)           │
│  [還原預設]                                             │
├─────────────────────────────────────────────────────────┤
│ Output 預測區                                           │
│  預測值: 115.0                                          │
│  規格: LSL=50 / USL=200                                 │
│  狀態: ● 在規格內 (Green) / ● 超規 (Red)                │
│  距離邊界: 85.0 (至 USL)                                │
└─────────────────────────────────────────────────────────┘
```

## 5. 預測邏輯

直接呼叫 `predict_output(model_type, coefficients, inputs)` 函數（與 Monte Carlo 共用）。

輸入範圍從資料統計取得（mean ± 3σ 或 min/max）。

## 6. 資料來源

- **模型**：`modeling/list` → 選擇已訓練模型
- **輸入範圍**：`data/distribution` → 取得各 input 的 mean, std, min, max
- **規格**：`spec`（ProcessDefine 階段設定）

## 7. 前端 API

```typescript
predictOutput(params: {
  model_id: string
  input_values: Record<string, number>
}): Promise<{ success: boolean; predicted: number; equation: string; inputs: string[] }>

getModelInfo(params: {
  model_id: string
}): Promise<{ success: boolean; model_type: string; inputs: string[]; coefficients: Record<string, number>; equation: string; n_train: number }>
```

## 8. 實現步驟

### Phase 10a — 後端
1. `prediction.py` — `predict_single()` 函數
2. `main.py` — `prediction/predict`, `prediction/model_info` handlers
3. `test_main_prediction.py` — 測試

### Phase 10b — 前端
4. `engine.ts` — API 封裝
5. `Prediction.tsx` — UI 組件
6. `App.tsx` + `Sidebar.tsx` — 路由整合
7. i18n en/zh-TW
