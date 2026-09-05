# AI 助手領域知識增強 — 設計規格 v1.0

日期：2026-09-05
狀態：設計討論中

## 目標

為 SPC、Monte Carlo、Exploration 頁面增強 AI 助手的領域知識，讓 AI 能更精準地解讀分析結果並提供專業建議。

## 範圍

### SPC 頁面向知識增強

1. **控制圖類型選擇指南**
   - I-MR：單個測量值（子群組大小=1）
   - X-bar+R：子群組大小 2-10，穩定變異
   - X-bar+S：子群組大小 ≥11，或變異差異大
   - EWMA：檢測小漂移（<1.5σ），加權平均
   - CUSUM：檢測持續性小偏移，累積偏差

2. **能力指數解讀**
   - Cp/Cpk ≥ 1.33：製程能力充足（綠）
   - 1.0 ≤ Cp/Cpk < 1.33：邊緣（橘）
   - Cp/Cpk < 1.0：能力不足（紅）
   - Cp vs Cpk：Cp 看潛在能力，Cpk 看實際中心偏移

3. **Western Electric 規則解讀**
   - Rule 1：單點超界 → 立即異常
   - Rule 2：2/3 點超 2σ → 趨勢開始
   - Rule 3：4/5 點超 1σ → 偏移徵兆
   - Rule 4：8 點同側 → 製程偏移
   - Rule 5：6 點遞增/遞減 → 漂移趨勢
   - Rule 6：15 點內 ±1σ → 變異減少（可能是分層）
   - Rule 7：14 點交錯 → 系統性變異

4. **優化建議解讀**
   - 低能力 → 減少變異或調整目標
   - 偏移偵測 → 檢查原料/機台參數
   - 趨勢偵測 → 檢查工具磨損/溫度漂移
   - 小漂移 → 即時調整

### Monte Carlo 頁面向知識增強

1. **NG 機率解讀**
   - < 0.1%：優秀
   - 0.1% - 1%：可接受
   - 1% - 5%：需注意
   - > 5%：高風險，需改善

2. **百分位數解讀**
   - P1/P99：極端情況範圍
   - P5/P95：正常操作範圍
   - P50：中位數（預測值）

3. **預測能力指數**
   - 與 SPC 的 Cpk 區別：模擬 vs 實際數據
   - 用於評估潛在製程表現

4. **異常風險排名**
   - 解讀各異常對 NG 的貢獻度
   - 優先處理高貢獻度異常

### Exploration 頁面向知識增強

1. **分布擬合解讀**
   - 如何選擇最佳分布（AIC/BIC/KS p-value）
   - 偏態/峰度意義

2. **時間序列特徵解讀**
   - lag 自動相關性
   - rolling mean/std 趨勢
   - drift 檢測

3. **GRR 解讀**
   - %GRR < 10%：可接受
   - 10% ≤ %GRR < 30%：邊緣
   - %GRR ≥ 30%：不可接受

## 設計

### 修改 `assistantGuide.ts`

擴充 `TAB_GUIDES` 中 `spc`、`monteCarlo`、`exploration` 的 `body` 欄位，加入詳細領域知識。

### 修改 `assistantData.ts`

Enhance `buildSpcContext`、`buildMonteCarloContext`、`buildExplorationContext` 提供更結構化的數據摘要。

### i18n

新增 ~15 keys 用於 AI 提示中的關鍵術語（可選，或直接硬編碼英文術語）。

## 驗證

- `npx tsc --noEmit` clean
- `npm run build` 成功
- 手動測試 AI 助手回答品質

## Commit 預期

1. `feat(assistant): enhance domain knowledge for SPC/MC/Exploration`
2. `docs` + push

## Files changed

- `src/lib/assistantGuide.ts`
- `src/lib/assistantData.ts`（可選增強）
- `docs/superpowers/specs/`（本文件）
