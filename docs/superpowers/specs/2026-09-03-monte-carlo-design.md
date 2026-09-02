# Phase 9 — 蒙地卡羅異常風險模擬：設計規格

## 1. 概述

結合 Phase 2 異常場景、Phase 8 SPC 分布分析、Model Center 已訓練模型，執行蒙地卡羅模擬，計算 output 分布、NG 機率與風險排名。

## 2. 範圍

### 納入
- DOE linear / quadratic 模型預測（係數直接計算）
- Input 變異抽樣（從 fitted distribution 抽取）
- 異常場景機率整合（獨立假設）
- 8 種圖表輸出
- NG 機率 + P1/P5/P50/P95/P99
- 模擬參數設定（次數、種子、啟用/停用異常）

### 不納入（後續 Phase）
- Random Forest / Hybrid 模型預測（需要 predict() API）
- Copula / 相關矩陣（僅獨立假設）
- 模擬結果持久化
- 即時資料串流

## 3. 架構

```
engine/src/process_intelligence_engine/monte_carlo.py  — 計算引擎
engine/src/process_intelligence_engine/main.py         — IPC handlers
src/lib/engine.ts                                      — API 封裝
src/features/monte-carlo/MonteCarlo.tsx                — UI 組件
```

### IPC handlers
- `monte_carlo/run` — 執行模擬並回傳所有結果

### 前端 API
```typescript
analyzeMonteCarlo(params: {
  dataset_id: string
  model_id: string
  input_columns: string[]
  output_column: string
  n_simulations: number
  seed: number
  enable_anomalies: boolean
  lsl?: number
  usl?: number
}): Promise<MonteCarloResult>
```

## 4. 計算流程

```
1. 載入 dataset + model + distribution fits + anomaly scenarios
2. 對每個 input：從 fitted distribution 抽樣 n_simulations 次
3. 若 enable_anomalies：
   - 對每個 anomaly scenario，依 occurrence_probability 決定是否發生
   - 若發生，從 magnitude_distribution 抽取幅度
   - 將幅度加到對應 input 值上
4. 計算交互作用項（若有）
5. 套用模型方程式計算 output
6. 判定 LSL/USL → NG
7. 計算統計量與圖表數據
```

## 5. 資料結構

```python
@dataclass
class MonteCarloResult:
    n_simulations: int
    seed: int
    ng_count: int
    ng_probability: float
    output_mean: float
    output_std: float
    output_median: float
    percentiles: dict  # {p1, p5, p50, p95, p99}
    histogram: dict    # {bins, counts}
    cdf_data: dict     # {x, y}
    boxplot_data: dict # {normal, single_anomaly, multi_anomaly}
    anomaly_rankings: list[dict]  # {anomaly_id, ng_contribution, probability}
    violations: list[dict]        # {simulation_idx, output, is_ng, anomalies}
```

## 6. 輸入分布抽樣

使用 Exploration 頁面的 distribution fit 結果：
- **normal**: `scipy.stats.norm(loc=mean, scale=sigma)`
- **gamma**: `scipy.stats.gamma(shape, loc=scale, scale=theta)`
- **lognormal**: `scipy.stats.lognorm(s=sigma, loc=mu, scale=exp(mu))`
- 其他: 使用 histogram 直方圖抽樣

## 7. 異常整合

- 每個 anomaly scenario 有 `occurrence_probability`
- 若發生，從 `magnitude_distribution` 抽取幅度
- 幅度加到對應 input 值（direction: above/below）
- 多個 anomaly 獨立隨機決定（P(A∩B) = P(A)·P(B)）

## 8. 模型預測

DOE linear: `y = β₀ + Σβᵢxᵢ`
DOE quadratic: `y = β₀ + Σβᵢxᵢ + Σβᵢⱼxᵢxⱼ + Σβᵢᵢxᵢ²`

係數從 `ModelFit.coefficients` 讀取（dict: {"intercept": ..., "x1": ..., "x1_x2": ...}）

## 9. 圖表輸出

1. **Output 直方圖** — 整體分布
2. **CDF 曲線** — 累積機率
3. **箱型圖** — 正常 vs 單一異常 vs 多重異常
4. **異常組合風險排名** — 表格
5. **NG 機率卡片** — 數字 + 色標
6. **百分位數卡片** — P1/P5/P50/P95/P99
7. **模擬設定摘要** — 次數、種子、啟用異常

## 10. UI 流程

1. 選擇模型（從既有模型下拉）
2. 確認 input/output 欄位
3. 設定模擬參數（次數、種子、啟用異常）
4. 按「執行模擬」
5. 顯示結果（卡片 + 圖表 + 表格）

## 11. 錯誤處理

- 模型尚未訓練 → 提示先至 Model Center 訓練
- 欄位角色未確認 → 提示先完成 Process Define
- 模擬次數過小 → 警告
- 模型外插 → 標記警告
