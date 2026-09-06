# v0.4.0 可信分析鏈規格書 (Trustworthy Analysis Chain)

**版本**: v0.4.0
**日期**: 2026-09-06
**作者**: Fred Wang
**狀態**: Draft for implementation
**前置條件**: v0.3.0 已完整部署

---

## 目錄

1. [產品定位與成功標準](#1-產品定位與成功標準)
2. [版本鏈基礎設施（Phase A）](#2-版本鏈基礎設施phase-a)
3. [分析階段閘門（Phase B）](#3-分析階段閘門phase-b)
4. [報告證據包（Phase C）](#4-報告證據包phase-c)
5. [模型治理規則（Phase D）](#5-模型治理規則phase-d)
6. [異常來源追蹤（Phase E）](#6-異常來源追蹤phase-e)
7. [驗證實驗閉環（Phase F）](#7-驗證實驗閉環phase-f)
8. [API 端點總覽](#8-api-端點總覽)
9. [測試策略](#9-測試策略)
10. [實施路線圖](#10-實施路線圖)

---

## 1. 產品定位與成功標準

### 1.1 定位轉變

v0.3.0 是「功能完整原型」。v0.4.0 轉向「分析可信度與工程落地」：

```
v0.3.0: 資料匯入 → 8 模型配適 → 蒙地卡羅 → 報告匯出（功能閉環）
v0.4.0: 資料匯入 → 階段確認 → 模型治理 → 驗證閉環 → 證據報告（可信閉環）
```

### 1.2 成功標準

v0.4.0 必須達成：

1. **追溯性**：任一報告結果可追溯回資料集 ID、模型版本、模擬種子
2. **可驗證性**：每個結論標明來源（AI 推測/統計顯著/工程假設/實驗已確認/未驗證）
3. **階段控制**：未完成/待確認/已確認三階段明確分界
4. **版本治理**：修改任何參數產生新版本，不覆蓋舊結果
5. **外插警告**：模型輸出若超出訓練範圍，報告明確標示

---

## 2. 版本鏈基礎設施（Phase A）

### 2.1 設計原則

- 中央管理器（`versioning/chain.py`）維護跨實體關聯
- 現有註冊表（`ModelRegistry`、`ReportRegistry`）不感知版本鏈
- 新增實體時只改 `chain.py`，不改現有註冊表
- UUID + 類型前綴（`ds-xxx`、`md-xxx`、`sim-xxx`、`rep-xxx`、`exp-xxx`）

### 2.2 資料結構

```python
@dataclass
class EntityRecord:
    entity_id: str           # UUID（ds-xxx, md-xxx, sim-xxx, rep-xxx, exp-xxx）
    entity_type: str         # "dataset" | "model" | "simulation" | "report" | "experiment"
    version: int             # monotonic counter per type
    metadata: dict           # 自由欄位（dataset_id, model_type, operator, seed 等）
    parent_id: str | None    # 父實體 ID
    created_at: str          # ISO 8601 UTC
    tags: list[str]          # e.g. ["verified", "cross_plotted"]
    source_label: str        # "ai_guess" | "stat_sig" | "eng_hypothesis" | "exp_confirmed" | "unverified"


@dataclass
class LinkRecord:
    from_id: str
    to_id: str
    relation: str            # "uses_dataset" | "trained_on" | "simulated_by" | "reported_in"
    source_label: str        # 同上
```

### 2.3 版本鏈管理器

```python
class VersionChain:
    def register_entity(self, entity_type: str, metadata: dict, parent_id: str | None = None) -> str
    def get_entity(self, entity_id: str) -> EntityRecord
    def add_link(self, from_id: str, to_id: str, relation: str, source_label: str = "unverified")
    def get_trace(self, entity_id: str) -> dict  # 完整追溯圖
    def get_chain_summary(self) -> list[dict]    # 所有實體的簡表
```

### 2.4 整合現有註冊表

在以下時機登記實體：

| 時機 | 實體類型 | 元數據欄位 |
|---|---|---|
| `data/import` | `dataset` | source_file, row_count, column_count |
| `modeling/fit` | `model` | model_type, dataset_id, n_train, n_test |
| `monte_carlo/run` | `simulation` | model_id, dataset_id, n_simulations, seed |
| `report/generate` | `report` | model_id, dataset_id, format, operator |
| `experiment/record` | `experiment` | model_id, dataset_id, actual_output |

### 2.5 版本鏈 API

```
GET  versioning/chain/summary          # 所有實體簡表
GET  versioning/chain/trace/:id        # 單一實體的完整追溯圖
POST versioning/chain/link            # 手動建立關聯
```

---

## 3. 分析階段閘門（Phase B）

### 3.1 設計原則

- **混合模式**：專案級總覽 + 模組級獨立控制
- 每個模組有獨立狀態：`not_started` / `pending_confirmation` / `confirmed`
- 報告產生時彙總各模組狀態，未確認模組的數據打標但不阻止報告生成

### 3.2 狀態機

```
not_started ──► pending_confirmation ──► confirmed
       ▲                    │
       └────────────────────┘
              (reset to review)
```

### 3.3 模組狀態表

| 模組 | 確認內容 |
|---|---|
| 資料匯入 | 欄位角色確認、品質檢查結果 |
| 製程定義 | 規格界限（LSL/USL）、管制界限（LCL/UCL）|
| 模型中心 | 最終模型選擇、模型狀態（approved）|
| SPC | 管制界限採用、違規判定 |
| 蒙地卡羅 | 模擬參數、異常機率來源 |
| 互動預測 | 預測情景保存 |
| 驗證實驗 | 實驗結果標記（支持/不支持）|

### 3.4 階段閘門 API

```
GET  gates/status                    # 所有模組狀態總覽
POST gates/confirm/:module           # 使用者確認某模組
POST gates/reset/:module             # 重置為待確認
GET  gates/summary                   # 報告產生時呼叫（彙總可用數據）
```

### 3.5 前端整合

- 專案總覽頁面新增「分析階段」Card，顯示各模組狀態
- 已確認模組：綠色勾 ✓
- 待確認模組：橙色 ⏳
- 未開始模組：灰色 ○

---

## 4. 報告證據包（Phase C）

### 4.1 報告新增章節

在現有 14 章節之外，新增以下證據鏈內容：

#### 4.1.1 報告首頁證據摘要

```
資料集版本: ds-abc123 | 版本: v1 | 筆數: 45 | 來源: test_dataset.csv
欄位角色: 5 input, 1 output, 1 quality_label（已確認）
資料品質: 2 warnings（缺失值 3%, 離群值 1 筆）
模型版本: md-xyz456 | 狀態: approved | R²: 0.92
模擬版本: sim-789abc | 種子: 42 | NG 機率: 2.3%
核准紀錄: 操作者 Fred, 2026-09-06 14:30 UTC, 備註: "模型已通過驗證"
未確認項目: 異常情境 #3（source=AI estimate, confidence=0.45）
```

#### 4.1.2  appendix A：版本鏈追溯

| 分析步驟 | 實體 ID | 操作者 | 時間 | 狀態 |
|---|---|---|---|---|
| 資料匯入 | ds-abc123 | Fred | 2026-09-06 10:00 | confirmed |
| 欄位辨識 | - | - | - | - |
| 模型配適 | md-xyz456 | Fred | 2026-09-06 10:15 | approved |
| 統計推論 | - | - | - | - |
| 蒙地卡羅 | sim-789abc | Fred | 2026-09-06 10:30 | confirmed |
| 驗證實驗 | exp-001 | Fred | 2026-09-06 11:00 | confirmed |
| 報告產生 | rep-def456 | Fred | 2026-09-06 14:30 | approved |

#### 4.1.3 appendix B：來源標籤解讀

| 標籤 | 含義 | 範例 |
|---|---|---|
| `ai_guess` | AI 模型推測，未經驗證 | 隨機森林特徵重要性 |
| `stat_sig` | 統計顯著（p<0.05）| DOE 係數 t 檢定 |
| `eng_hypothesis` | 工程假設 | 工程情境異常 |
| `exp_confirmed` | 實驗已確認 | 驗證實驗支持模型 |
| `unverified` | 未驗證 | 預設狀態 |

#### 4.1.4 appendix C：外插警告統計

- 預測點落在訓練範圍外的比例
- 每個輸入變數的外插風險分數
- 建議：是否補做驗證實驗

### 4.2 ReportData 擴充

```python
@dataclass
class ReportData:
    # 既有欄位（保持向後相容）
    project_name: str
    operator: str
    # ... 原有欄位 ...
    
    # 新增證據鏈欄位
    chain_trace: dict = field(default_factory=dict)      # 版本鏈追溯
    source_labels: dict = field(default_factory=dict)    # 各結論的來源標籤
    gate_summary: dict = field(default_factory=dict)     # 階段閘門狀態
    approval_record: dict | None = None                  # 核准紀錄
    unconfirmed_items: list[str] = field(default_factory=list)  # 未確認項目清單
    extrapolation_summary: dict = field(default_factory=dict)   # 外插警告統計
```

### 4.3 HTML 報告新增

- 報告首頁新增「證據摘要」block
- 報告尾部新增三個 appendix（版本鏈追溯、來源標籤、外插警告）
- 未確認項目以 warning badge 顯示

---

## 5. 模型治理規則（Phase D）

### 5.1 模型適用性檢查

在 `fitModel` 前執行以下檢查，不滿足條件時顯示警告或阻止：

| 檢查項目 | 條件 | 行為 |
|---|---|---|
| 最小樣本數 | n < 30 | 警告，tree models 禁止 |
| 類別失衡 | OK/NG 比例 > 4:1 | 警告，logistic 回歸效果不可信 |
| 多重共線性 | VIF > 10 | 警告，建議移除相關變數 |
| 常數欄位 | 唯一值 = 1 | 自動排除 |
| 外插風險 | 預測點超出訓練範圍 | 在預測時警告 |

### 5.2 DOE 退回規則

當 DOE 與 AI 模型預測差異過大時，自動建議退回 DOE：

```python
def check_doeb_ai_discrepancy(
    doe_r2: float,
    ai_r2: float,
    ai_pred: list[float],
    doe_pred: list[float],
    threshold: float = 0.15
) -> dict:
    """檢查 DOE 與 AI 預測差異."""
    abs_diff = [abs(a - b) for a, b in zip(ai_pred, doe_pred)]
    max_diff = max(abs_diff)
    mean_diff = sum(abs_diff) / len(abs_diff)
    
    should_retreat = max_diff > threshold or mean_diff > threshold
    
    return {
        "should_retreat": should_retreat,
        "max_difference": max_diff,
        "mean_difference": mean_diff,
        "recommendation": "建議退回 DOE 模型" if should_retreat else "AI 模型可接受",
    }
```

### 5.3 選模推薦

根據資料特徵推薦最適合的模型（而非列出全部 8 種）：

```python
def recommend_models(
    n_samples: int,
    n_features: int,
    is_binary_target: bool,
    has_nonlinearity: bool,
    need_interpretability: bool
) -> list[str]:
    """推薦適合的模型類型."""
    recommendations = []
    
    if is_binary_target:
        recommendations.append("logistic_regression")
        if n_samples >= 100:
            recommendations.append("xgboost")
    else:
        # 連續目標
        if n_samples < 50:
            recommendations.append("doe_linear")
            if n_features >= 2:
                recommendations.append("doe_quadratic")
        elif n_samples < 200:
            recommendations.append("doe_quadratic")
            if has_nonlinearity:
                recommendations.append("residual_hybrid")
        else:
            if need_interpretability:
                recommendations.append("doe_linear")
                recommendations.append("residual_hybrid")
            else:
                recommendations.append("xgboost")
                recommendations.append("lightgbm")
    
    # 樣本充足時可考慮隨機森林
    if n_samples >= 100 and not need_interpretability:
        recommendations.append("random_forest")
    
    return recommendations
```

### 5.4 模型治理 API

```
GET  modeling/governance/check            # 執行適用性檢查
POST modeling/governance/fit_with_check   # 配適前執行檢查（含警告）
GET  modeling/governance/recommend        # 根據資料特徵推薦模型
POST modeling/governance/doe_ai_compare   # 比較 DOE vs AI 差異
```

---

## 6. 異常來源追蹤（Phase E）

### 6.1 設計目標

每個異常情境必須明確標示：
- **發生機率來源**：歷史資料 / 工程輸入 / AI 推估 / 使用者覆寫
- **信心度**：0.0 ~ 1.0
- **使用者確認狀態**：user_confirmed

### 6.2 現有基礎

`AnomalyScenario` 已有 `source`、`confidence`、`user_confirmed` 欄位：

```python
@dataclass
class AnomalyScenario:
    source: str = "historical_observation"  # 已有
    confidence: float = 0.0                  # 已有
    user_confirmed: bool = False             # 已有
    # ... 其他欄位 ...
```

### 6.3 需要新增的功能

1. **來源可選清單**：前端 UI 允許選擇 source（historical_observation / engineering_input / ai_estimate / user_override）
2. **信心度滑桿**：根據 source 預設信心度，可手動調整
3. **來源追蹤記錄**：每次修改 source/confidence 產生新版本記錄

### 6.4 版本鏈整合

異常情境變更時登記為獨立實體：

```python
# 在 anomalies.py 新增
def register_anomaly_event(
    chain: VersionChain,
    dataset_id: str,
    anomaly_id: str,
    source: str,
    confidence: float,
    user_confirmed: bool,
    operator: str,
) -> str:
    """登記異常情境事件到版本鏈."""
    entity_id = chain.register_entity(
        entity_type="anomaly",
        metadata={
            "dataset_id": dataset_id,
            "anomaly_id": anomaly_id,
            "source": source,
            "confidence": confidence,
            "user_confirmed": user_confirmed,
            "operator": operator,
        }
    )
    chain.add_link(entity_id, dataset_id, "derived_from", source_label=source)
    return entity_id
```

---

## 7. 驗證實驗閉環（Phase F）

### 7.1 現有基礎

`ExperimentRegistry` 和 `experiment/record` 已存在。需要強化：

1. **結果標記**：支持/部分支持/不支持/需重新建模
2. **自動觸發模型狀態更新**
3. **下次實驗建議**

### 7.2 實驗結果標記

```python
EXPERIMENT_VERDICT = {
    "supports": "支持模型",
    "partially_supports": "部分支持",
    "does_not_support": "不支持",
    "needs_remodel": "需重新建模",
}
```

判定邏輯：

```python
def compute_experiment_verdict(
    predicted: float,
    actual: float,
    tolerance: float = 0.1  # 10% 誤差容限
) -> str:
    """根據預測誤差計算實驗結論."""
    if predicted == 0:
        abs_error = abs(actual)
    else:
        abs_error = abs(actual - predicted) / abs(predicted)
    
    if abs_error <= tolerance * 0.5:
        return "supports"
    elif abs_error <= tolerance:
        return "partially_supports"
    elif abs_error <= tolerance * 2:
        return "does_not_support"
    else:
        return "needs_remodel"
```

### 7.3 模型狀態自動更新

當實驗結果為 `does_not_support` 或 `needs_remodel` 時：

```python
def update_model_after_experiment(
    model_id: str,
    verdict: str,
    chain: VersionChain,
) -> None:
    """根據實驗結論更新模型狀態."""
    model = MODEL_REGISTRY.get(model_id)
    
    if verdict in ("does_not_support", "needs_remodel"):
        # 退回 draft，提示重新配適
        if model.status in ("approved", "validated"):
            MODEL_REGISTRY.transition(model_id, "retired")
            # 自動產生新版本（保留歷史）
            chain.add_link(
                from_id=model_id,
                to_id=model_id,  # 新 ID 由呼叫端產生
                relation="replaced_by",
                source_label="exp_confirmed"
            )
```

### 7.4 下次實驗建議

基於當前模型的不確定度自動計算：

```python
def recommend_next_experiment(
    model_id: str,
    df: pd.DataFrame,
    n_suggestions: int = 3
) -> list[dict]:
    """基於模型不確定度推薦下次實驗條件."""
    model = MODEL_REGISTRY.get(model_id)
    
    # 使用 SHAP 不確定度或預測區間寬度
    # 優先選擇：
    # 1. 模型預測最好與最差的條件
    # 2. output 接近規格邊界的條件
    # 3. 模型不確定度最高的條件
    
    suggestions = []
    # ... 計算邏輯 ...
    return suggestions
```

### 7.5 驗證實驗 API 擴充

```
POST experiment/record_with_verdict  # 記錄實驗 + 自動計算 verdict
GET  experiment/suggest_next/:model_id  # 自動推薦下次實驗條件
POST experiment/impact/:model_id   # 記錄實驗結果對模型的影響
```

---

## 8. API 端點總覽

### 8.1 版本鏈（新增）

| 端點 | 方法 | 功能 |
|---|---|---|
| `versioning/chain/summary` | GET | 所有實體簡表 |
| `versioning/chain/trace/:id` | GET | 單一實體追溯圖 |
| `versioning/chain/link` | POST | 手動建立關聯 |

### 8.2 階段閘門（新增）

| 端點 | 方法 | 功能 |
|---|---|---|
| `gates/status` | GET | 所有模組狀態 |
| `gates/confirm/:module` | POST | 確認某模組 |
| `gates/reset/:module` | POST | 重置為待確認 |
| `gates/summary` | GET | 彙總可用數據 |

### 8.3 模型治理（新增）

| 端點 | 方法 | 功能 |
|---|---|---|
| `modeling/governance/check` | GET | 適用性檢查 |
| `modeling/governance/fit_with_check` | POST | 配適 + 檢查 |
| `modeling/governance/recommend` | GET | 推薦模型 |
| `modeling/governance/doe_ai_compare` | POST | DOE vs AI 差異檢查 |

### 8.4 驗證實驗（擴充）

| 端點 | 方法 | 功能 |
|---|---|---|
| `experiment/record_with_verdict` | POST | 記錄 + 自動判定 |
| `experiment/suggest_next/:model_id` | GET | 推薦下次實驗 |
| `experiment/impact/:model_id` | POST | 記錄影響 |

### 8.5 現有端點不變

所有 v0.3.0 的 API 端點保持向後相容。

---

## 9. 測試策略

### 9.1 引擎測試

- **版本鏈**：`test_versioning_chain.py`（15 測試）
  - 實體登記、追溯查詢、關聯建立、版本 counter
- **階段閘門**：`test_gates.py`（10 測試）
  - 狀態轉換、彙總邏輯、reset 行為
- **模型治理**：`test_governance.py`（12 測試）
  - 適用性檢查、DOE vs AI 差異、選模推薦
- **驗證實驗**：`test_experiment_verdict.py`（8 測試）
  - verdict 判定、模型狀態自動更新、下次實驗建議

### 9.2 端到端測試

- 完整流程測試：匯入 → 確認 → 配適 → 驗證 → 報告生成
- 版本鏈完整性驗證
- 報告證據包內容驗證

### 9.3 測試目標

- 新增測試 ≥ 45 支
- 現有測試無回歸
- 目標覆蓋率 ≥ 80%

---

## 10. 實施路線圖

### Phase A（版本鏈基礎）— 預計 3-4 天

1. 建立 `versioning/chain.py`
2. 整合現有註冊表（ModelRegistry、ReportRegistry、ExperimentRegistry）
3. 新增 3 個 IPC 端點
4. 15 支測試

### Phase B（階段閘門）— 預計 2-3 天

1. 建立 `gates/manager.py`
2. 前端「分析階段」Card
3. 4 個 IPC 端點
4. 10 支測試

### Phase C（報告證據包）— 預計 2-3 天

1. `ReportData` 擴充
2. HTML 報告新增證據摘要 + appendix
3. 整合版本鏈追溯
4. 前端 Report.tsx 更新

### Phase D（模型治理）— 預計 3-4 天

1. 適用性檢查函數
2. DOE vs AI 差異檢查
3. 選模推薦
4. 12 支測試

### Phase E（異常來源追蹤）— 預計 1-2 天

1. 前端異常情境 UI 增強（source 選擇、信心度滑桿）
2. 版本鏈登記異常事件
3. 2 支測試

### Phase F（驗證實驗閉環）— 預計 2-3 天

1. 實驗 verdict 計算
2. 模型狀態自動更新
3. 下次實驗建議
4. 8 支測試

**總計：13-19 天**

---

## 附錄 A：版本前綴對照表

| 實體類型 | 前綴 | 範例 ID |
|---|---|---|
| 資料集 | `ds` | `ds-a1b2c3d4` |
| 模型 | `md` | `md-e5f6g7h8` |
| 模擬 | `sim` | `sim-i9j0k1l2` |
| 報告 | `rep` | `rep-m3n4o5p6` |
| 實驗 | `exp` | `exp-q7r8s9t0` |
| 異常情境 | `ano` | `ano-u1v2w3x4` |

---

## 附錄 B：來源標籤對照表

| 標籤鍵 | 中文 | 英文 |
|---|---|---|
| `ai_guess` | AI 推測 | AI guess |
| `stat_sig` | 統計顯著 | Statistically significant |
| `eng_hypothesis` | 工程假設 | Engineering hypothesis |
| `exp_confirmed` | 實驗已確認 | Experiment confirmed |
| `unverified` | 未驗證 | Unverified |

---

## 附錄 C：不納入 v0.4.0 的項目

以下項目明確排除：

1. **AI 助手面板** — 留待 v0.5.0
2. **即時 MES 連線** — 不符合第一版範圍
3. **影像深度學習** — 不符合第一版範圍
4. **更複雜的 UI 美化** — 優先級低於功能
5. **GPU 最佳化** — 留待 v0.5.0

---

*End of v0.4.0 spec.*
