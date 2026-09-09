# v0.8.0 Data Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 建立資料匯入後的 input/output 健檢、分布診斷與建模前 Gate。

**Architecture:** 後端新增可重複執行的 readiness 分析服務與結果 DTO；前端在資料匯入完成後顯示診斷總覽，並將快照提供給 AI、報告與模型配適。既有探索分布 API 保持不變，readiness 只負責批次前置掃描。

**Tech Stack:** Python engine、pandas/scipy、React/TypeScript、Ant Design、Plotly、i18next。

**Spec:** `docs/superpowers/specs/2026-09-09-v080-data-readiness-design.md`

## Global Constraints

- 版本來源為 `VERSION`，固定為 `0.8.0`。
- 不以自動分布判定替代模型驗證或工程確認。
- 保持既有資料匯入、探索、SPC、GRR 與模型流程相容。

### Task 1: Readiness engine contract

**Files:** `engine/src/process_intelligence_engine/data/readiness.py`, `engine/src/process_intelligence_engine/main.py`, `engine/tests/test_readiness.py`

- [ ] 先寫測試：正常數值欄位回傳摘要、缺失與常數欄位產生警告、無有效值產生阻擋。
- [ ] 新增 `analyze_readiness(df, fields)`，回傳每欄位診斷與 overall_status。
- [ ] 新增 IPC `data/readiness`，使用已載入 dataset_id 與欄位角色。
- [ ] 執行 `pytest engine/tests/test_readiness.py -q`。

### Task 2: Frontend readiness panel

**Files:** `src/lib/engine.ts`, `src/features/data-import/DataImport.tsx`, `src/features/data-readiness/Readiness.tsx`, `src/i18n/*.json`

- [ ] 先寫元件測試，確認每個 input/output 顯示狀態、分布與品質摘要。
- [ ] 匯入完成後呼叫 `data/readiness`，顯示表格、狀態標籤與欄位分布圖。
- [ ] 阻擋項目提供回到欄位角色／品質檢查的導引；不自動修改資料。
- [ ] 補齊繁中、英文、西文翻譯。
- [ ] 執行前端測試與 `npm run build`。

### Task 3: Context, Gate and report integration

**Files:** `src/lib/assistantData.ts`, `src/features/model-center/ModelCenter.tsx`, `src/features/report/Report.tsx`, `engine/src/process_intelligence_engine/main.py`, tests

- [ ] 將 readiness 摘要加入 AI 上下文，包含欄位、狀態、分布與問題。
- [ ] 模型配適前顯示 readiness 狀態；阻擋時禁止開始配適並提供原因。
- [ ] 報告 metadata 保存 readiness snapshot 與 dataset_id。
- [ ] 執行跨流程整合測試，確認匯入→健檢→模型／報告資料一致。

### Task 4: Documentation and release verification

**Files:** `README.md`, `README_CHT.md`, `docs/`, `VERSION` generated files

- [ ] 更新 v0.8.0 功能總覽、流程與限制。
- [ ] 執行完整前後端測試、版本同步檢查與 production build。
- [ ] 產生 release notes，確認所有版本檔為 0.8.0。
