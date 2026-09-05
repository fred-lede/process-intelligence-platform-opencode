# HANDOFF.md

## Milestone: 製程流程 × 下游分析整合（ProcessFlow ↔ Downstream Analysis）完成

**日期**: 2026-09-05

**里程碑**: 10-task ProcessFlow↔downstream-analysis integration 全部完成並 merge 至 main（含 Task 10 hardening）。

### 交付內容

- **引擎**：`ProjectManifest.association_keys` + `set_association_keys()`；`filter_column`/`filter_value` df-level mask 統一為 `_apply_row_filter` helper（SPC analyze / monte_carlo run / data distribution / data series 4 handler，含 zero-row `ValueError("No rows match filter")` 守衛）
- **前端**：`processFlowNavStore` + `processFlowContext.ts` 跳轉基礎設施；ProcessFlow 關聯鍵 UI + 跳轉按鈕；App 訂閱切 tab；SPC / Monter-Carlo / Exploration 消費跳轉上下文（StrictMode-safe）+ 共用 `NodeSourceFilter` 元件（`filterable` 控制 time-series/GRR 不顯示 filter）
- **i18n**：三語（en / zh-TW / es-MX）`processFlow`/`spc`/`monteCarlo`/`exploration` key-set parity `ok`
- **驗證**：全引擎 **304 passed, 1 skipped**；`npx tsc --noEmit` clean；`npm run build` 成功

### Commits（本里程碑）

`cd7788e, 7db24b8, e0f85dd, 570d01c, b535cd0, 26f3b89, 74e44f4, c22c283, a15e04c, 9e3d2b9, b7f3100, 878f821, 8160797, 4ab2313, c76aff4, 62ce296, 909bf76` + Task 10 (`feat(engine)` zero-row guard / `fix(spc)` numeric guard / `docs`)

### Known Follow-ups

1. **time-series / GRR 不套用節點 filter**：Exploration time-series/GRR tabs 前端 `filterable=false` 隱藏控制，引擎通道未接（有意範圍裁剪）
2. **dev StrictMode 一次性跳轉語意**：`consume()` 為破壞性清空（production 正常，dev 有既有 mount-effect 守衛）
3. **數值欄 filter 比較注意**：`astype(str) == str(value)` 對數值欄（`50.0` vs `"50"`）可能 0 列；現已由 zero-row `ValueError` 明確提示（不靜默）

### 下一步方向（供後續任務參考）

- 節點篩選延伸至 time-series / GRR
- 引擎 `filter_value` 空字串（`""`）防護
- 跳轉前未載入資料時「資料載入後自動補選」fallback