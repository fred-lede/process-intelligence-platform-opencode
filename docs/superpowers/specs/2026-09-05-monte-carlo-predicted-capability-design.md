# 蒙地卡羅預測能力指數（Pp/Ppk, simulation-based）— 設計規格

日期：2026-09-05
狀態：設計已批准（user 於 brainstorming 選定：Pp/Ppk、引擎端計算）

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

在 `run_monte_carlo`（monte_carlo.py:206）回傳 dict（:375-392）新增：

```python
"capability": compute_capability(output_values, lsl=lsl, usl=usl, subgroup_size=1),
```

- import：`from .spc import compute_capability`（spc.py 無回依賴動態 module 需確認——monte_carlo.py
  目前未 import spc，需驗證無 circular import）
- `lsl`/`usl` 參數 `run_monte_carlo` 已收（main.py:1123-1124 傳入）；兩側都設時
  `pp`/`ppk` 為數值，任缺一側時為 `None`（spc.py:80-86）
- `output_values` 已計算存在（:390 回傳 .tolist()），無額外成本
- **TDD 測試**（test_main_monte_carlo.py）：
  1. 有 lsl/usl → capability.pp/ppk 存在，且 pp == (usl-lsl)/(6*output_std)（ddof=1）、
     ppk == min((usl-mean), (mean-lsl))/(3*output_std)（與回傳 output_mean/output_std 比對）
  2. 無 lsl/usl → capability.pp 為 None / ppk 為 None

### 前端（engine.ts + MonteCarlo.tsx）

- `engine.ts`：`MonteCarloResult` interface 加 `capability?: SPCCapability | null`
  （重用既有 `SPCCapability`，engine.ts:649）
- `MonteCarlo.tsx`：現有 4 張統計卡 Row（:182-216）下方加一張
  「預測能力指數（simulation-based）」Card，欄位：
  - **Pp**：值 + antd Tag 色（≥1.33 success / ≥1.0 warning / else error）
  - **Ppk**：值 + 同上色標（SPC.tsx:126-127 同門檻）
  - 下方小字 σ（= capability.sigma_overall）
  - 僅當 `result.capability && capability.pp != null && capability.ppk != null` 才渲染
  - 無 spec 時不顯示（不顯示空卡片）

### AI 助手 context（assistantData.ts）

`buildMonteCarloContext`（monte_carlo.tsx:76 → lib/assistantData `buildMonteCarloContext`）
在現有情境後補一行：

```
Predicted capability (simulation): Pp=Pp, Ppk=Ppk (if present).
```

### i18n（en / zh-TW / es-MX）

`monteCarlo.*` 新增 4 keys，三語一致（key set parity 以 en 為 source of truth）：

| key | en | zh-TW |
|---|---|---|
| `predictedCapability` | Predicted Capability (simulation) | 預測能力指數（模擬） |
| `pp` | Pp | Pp |
| `ppk` | Ppk | Ppk |
| `sigmaOverall` | σ overall | σ 整體 |

（es-MX 對應翻譯，interpolation 變數一致）

## 驗證

- 引擎 full suite：red（新增 2 測試 FAIL）→ green；既有 **304 passed, 1 skipped** 維持
- `npx tsc --noEmit` clean
- `npm run build` 成功（chunk 警示為既有）
- 三語 `monteCarlo` key-set parity ok、JSON 有效

## Files changed（預期）

- `engine/src/process_intelligence_engine/monte_carlo.py`
- `engine/src/process_intelligence_engine/spc.py`（僅確認 import 依賴，不應改）
- `engine/tests/test_main_monte_carlo.py`
- `src/lib/engine.ts`
- `src/features/monte-carlo/MonteCarlo.tsx`
- `src/lib/assistantData.ts`
- `src/i18n/en.json` / `zh-TW.json` / `es-MX.json`
- docs（PROGRESS / TASK / README）