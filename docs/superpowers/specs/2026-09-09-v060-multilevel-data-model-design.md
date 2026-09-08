# v0.6.0 多層級資料模型設計規格

## 目標

在不破壞 v0.5.0 單層 CSV／Excel 相容性的前提下，讓資料可表達量測事件、產品、批次、機台、站點、製程步驟與子群組關係。

## 核心資料契約

每筆量測事件可使用以下欄位：`measurement_id`、`product_id`、`lot_id`、`machine_id`、`station_id`、`process_step`、`timestamp`、`subgroup_id`、`metric`、`value`、`unit`。既有任意欄位仍可保留。

## 相容性

- 沒有 metadata 欄位的 CSV 仍視為單層資料列。
- 現有 SPC、模型、模擬、報告 API 維持既有參數相容。
- 原始匯入資料不可覆寫；階層欄位與聚合結果皆為衍生 metadata／view。

## v0.6.0 範圍

- 匯入時偵測與保存標準 metadata 欄位。
- 提供依 lot、machine、station、process_step、timestamp 的篩選。
- SPC 支援以 subgroup_id 或指定分層欄位建立子群組。
- 版本鏈與 AI 上下文記錄資料粒度與篩選條件。

## 不納入

MES 即時連線、資料庫遷移、跨專案資料湖、完整事件溯源 UI 與自動因果推論。
