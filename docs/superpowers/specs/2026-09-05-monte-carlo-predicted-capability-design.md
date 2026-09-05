# 蒙地卡羅預測能力指數（Pp/Ppk, simulation-based）— 設計規格 v1.1

日期：2026-09-05
狀態：**Done**（2026-09-05 實作完成 + polish）

## 目標

在蒙地卡羅結果頁呈現「預測性製程能力指數」Pp / Ppk：用模擬輸出的整體 σ 計算，
明確標示 simulation-based，語意上不與 SPC 的 Cp/Cpk（量測實際製程）混淆。

## 動機

- SPC 頁的 Cp/Cpk 衡量「目前實際製程」；蒙地卡羅的價值在於前瞻——在指定輸入分布與
  異常情境下，預期會得到的能力水準。
- 模擬輸出的 σ 屬整體 σ，能力指數語意上是 **Pp/Ppk**（Cp/Cpk 需要子群內變異估計），
  user 已確認以 Pp/Ppk 呈現。

## 範圍（included）

1. 引擎（TDD）：`run_monte_carlo` 回傳 dict 加 `capability`
2. 前端：`MonteCarloResult` 型別 + 結果頁預測能力卡片
3. AI 助手 context：`buildMonteCarloContext` 補一行 Pp/Ppk
4. i18n：`monteCarlo.*` 新增 4 keys，三語同步

## 範圍（excluded / 不在本次）

- Cp/Cpk 不顯示（user 選定 Pp/Ppk）
- 4σ/5σ 分級不加（沿用 SPC ≥1.33 / ≥1.0 門檻）
- 引擎不改 `spc.capability` IPC handler；不新增 IPC，欄位掛在既有 `monte_carlo/run` 回傳

## 設計

### 引擎（monte_carlo.py）

`compute_capability`（spc.py:36）為既有單一能力指數來源，signature：
`compute_capability(values, lsl=None, usl=None, subgroup_size=1)`。
`subgroup_size=1` 時 σ_within = 整體 σ（spc.py:54-57），恰為 Pp/Ppk 語意。

在 `run_monte_carlo` 回傳 dict 新增：

```python
"capability": compute_capability(output_values, lsl=lsl, usl=usl, subgroup_size=1),
```

- import：`from .spc import compute_capability`（spc.py 無回依賴，無 circular import）
- `lsl`/`usl` 參數 `run_monte_carlo` 已收（main.py:1123-1124 傳入）；兩側都設時
  `pp`/`ppk` 為數值，任缺一側時為 `None`（spc.py:80-86）
- `output_values` 已計算存在（回傳 .tolist()），無額外成本
- **TDD 測試**（test_main_monte_carlo.py）：
  1. 有 lsl/usl → capability.pp/ppk 存在，且 pp == (usl-lsl)/(6*output_std)（ddof=1）、
     ppk == min((usl-mean), (mean-lsl))/(3*output_std)（與回傳 output_mean/output_std 比對）；
     σ_overall == approx(output_std, rel=1e-5)（6 dp rounding 容許 rel=1e-5）
  2. 無 lsl/usl → capability.pp 為 None / ppk 為 None

### 前端（engine.ts + MonteCarlo.tsx）

- `engine.ts`：`MonteCarloResult` interface 加 `capability?: SPCCapability | null`
  （重用既有 `SPCCapability`，engine.ts:649，字段含 cp/cpk/pp/ppk/sigma_within/sigma_overall/mean/n_subgroups/total_observations）
- `MonteCarlo.tsx`：現有 4 張統計卡 Row（NG/Mean/Median/Multi-Anomaly）下方加一張
  「預測能力指數（simulation-based）」Card，欄位：
  - **Pp**：antd Statistic，`precision={2}`，valueStyle 色標 ≥1.33 `#52c41a`（綠）
    / ≥1.0 `#fa8c16`（橘）/ <1.0 `#ff4d4f`（紅）
  - **Ppk**：同上色標
  - 右側小字 σ（`capability.sigma_overall.toFixed(2)`）
  - **僅當 `result.capability && capability.pp != null && capability.ppk != null && capability.sigma_overall != null` 才渲染**
  - 無 spec 時不顯示（不顯示空卡片）
- `capColor` helper：`(val: number) => val >= 1.33 ? '#52c41a' : val >= 1.0 ? '#fa8c16' : '#ff4d4f'`
  （與 SPC.tsx `capacityColor` 完全一致，threshold 與 hex 同）

### AI 助手 context（assistantData.ts）

`buildMonteCarloContext` 在「Top anomaly」行後新增條件式一行：

```ts
if (result.capability && result.capability.pp != null && result.capability.ppk != null && result.capability.sigma_overall != null) {
  lines.push(`Predicted capability (simulation): Pp=${num(result.capability.pp)}, Ppk=${num(result.capability.ppk)}, sigma_overall=${num(result.capability.sigma_overall)}.`)
}
```

三 guard（pp / ppk / sigma_overall 皆非 null）與 UI 卡對稱。`num()` 為既有 helper（null → `'N/A'`）。

### i18n（en / zh-TW / es-MX）

`monteCarlo.*` 新增 4 keys，三語一致（key set parity 以 en 為 source of truth）：

| key | en | zh-TW | es-MX |
|---|---|---|---|
| `predictedCapability` | Predicted Capability (simulation) | 預測能力指數（模擬） | Capacidad prevista (simulación) |
| `pp` | Pp | Pp | Pp |
| `ppk` | Ppk | Ppk | Ppk |
| `sigmaOverall` | σ overall | σ 整體 | σ general |

（parity 驗證：`python3 -c "import json; ks=[set(json.load(open('src/i18n/%s.json'%f))['monteCarlo']) for f in ('en','zh-TW','es-MX')]; print('parity ok:', ks[0]==ks[1]==ks[2], 'count:', len(ks[0]))` 輸出 `parity ok: True count: 34`）

## 實作後續 polish（v1.1 新增）

2026-09-05 實作完成後依 code review 與 user 回饋做以下 polish，已納入本版本：

1. **SPC 管制線圖例**（commit `1d2cb57`）：移除所有管制線 `showlegend: false`（UCL/LCL/CL/MR UCL+CL/R UCL+CL/S UCL+CL 共 12 處）→ 圖例可見橘虛=UCL/LCL、綠虛=CL、紫實=MR/R/S、紅實=LSL/USL；違規點仍隱藏
2. **MC σ 精度對齊**（commit `1d2cb57`）：`.toFixed(3)` → `.toFixed(2)` 與 Pp/Ppk `precision={2}` 一致
3. **MC AI context guard 對稱**（commit `1d2cb57`）：context guard 補 `sigma_overall != null`，與 UI 卡三 guard 一致

## 驗證

- 引擎 full suite：**306 passed, 1 skipped**（baseline 304 + 2 新測試）
- `npx tsc --noEmit` clean
- `npm run build` 成功（chunk 警示為既有，非本次引入）
- 三語 `monteCarlo` key-set parity ok、JSON 有效

## Commit 序列

| commit | 訊息 |
|---|---|
| `bb1b019` | feat(engine): monte carlo predicted capability (Pp/Ppk) via compute_capability |
| `27eb722` | feat(monte-carlo): predicted capability (Pp/Ppk) card, AI context, i18n |
| `a08c7e3` | docs: monte carlo predicted capability (Pp/Ppk) |
| `1d2cb57` | fix(spc/monte-carlo): show control limits in legend; sync σ precision & guard |
| `43e8b9d` | docs: TASK.md update for SPC legend + MC σ/guard polish |

## Files changed（最終）

- `engine/src/process_intelligence_engine/monte_carlo.py`（+1 import +1 dict entry）
- `engine/tests/test_main_monte_carlo.py`（+2 測試）
- `src/lib/engine.ts`（+1 欄位）
- `src/features/monte-carlo/MonteCarlo.tsx`（+1 helper +1 card +1 Statistic import）
- `src/lib/assistantData.ts`（+1 guard +1 行 context）
- `src/features/spc/SPC.tsx`（polish：12 處 showlegend:false 移除）
- `src/i18n/en.json` / `zh-TW.json` / `es-MX.json`（各 +4 keys）
- docs（PROGRESS / TASK / README / spec / plan）
