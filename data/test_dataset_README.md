# 預存測試資料說明

## 檔案：data/test_dataset.csv

### 欄位說明

| 欄位 | 名稱 | 類型 | 範例值 | 說明 |
|------|------|------|--------|------|
| lot | 批次 | 類別 | L240901-A | 生產批次 |
| serial_no | 序號 | 類別 | SNC-0001 | 產品序號 |
| datetime | 時間 | 類別 | 2026-09-01 08:07:00 | 生產時間戳記 |
| machine | 機台 | 類別 | Line-A / Line-B | 生產線別 |
| operator | 操作者 | 類別 | O-01 / O-02 / O-03 | 作業員 |
| part | 零件 | 類別 | P-01 ~ P-05 | 零件型號 |
| input_temperature | 溫度 | 輸入（連續） | 81.84 | 製程溫度（°C）|
| input_voltage | 電壓 | 輸入（連續） | 11.355 | 供電電壓（V）|
| input_pressure | 壓力 | 輸入（連續） | 3.058 | 製程壓力（MPa）|
| input_speed | 轉速 | 輸入（連續） | 116.9 | 轉速（RPM）|
| input_load | 負載 | 輸入（連續） | 65.53 | 負載（N）|
| output_thickness | 厚度 | 輸出（連續） | 1.6177 | 成品厚度（mm）|
| result | 結果 | 輸出（二元） | OK / NG | 品質結果 |

### 資料特性

- **樣本數**：45 筆
- **輸入變數**：5 個（input_temperature, input_voltage, input_pressure, input_speed, input_load）
- **連續輸出**：1 個（output_thickness）
- **二元標籤**：1 個（result：OK/NG）
- **類別變數**：6 個（lot, serial_no, datetime, machine, operator, part）

### 適用模型

| 模型類型 | 適用欄位 | 說明 |
|----------|----------|------|
| doe_linear | output_thickness | 線性 DOE，需 ≥3 輸入 |
| doe_quadratic | output_thickness | 二次 DOE，含交互作用 |
| random_forest | output_thickness | 隨機森林，非線性 |
| xgboost | output_thickness | 梯度提升，高維 |
| lightgbm | output_thickness | 高效梯度提升 |
| residual_hybrid | output_thickness | DOE + RF 殘差混合 |
| logistic_regression | result | 二元分類（OK/NG）|
| weibull_regression | output_thickness | 可靠度/壽命分析 |

### 建議測試流程

1. **匯入資料**
   - 開啟「資料匯入」TAB
   - 上傳 `data/test_dataset.csv`（或點擊「下載 CSV 範本」取得相同格式）
   - 確認欄位角色：5 個 input、output_thickness 為 output、result 為 quality_label

2. **製程定義**
   - 開啟「製程定義」TAB
   - 設定 output_thickness 規格：LSL=1.60, USL=1.65
   - 可手設 LCL/UCL 或開啟自動 3σ 管制線

3. **模型配適**
   - 開啟「模型中心」TAB
   - 連續輸出：測試 DOE 線性、DOE 二次、隨機樹、XGBoost、LightGBM、殘差混合
   - 二元輸出：選 result 作為目標，測試 Logistic 迴歸
   - 壽命分析：選 output_thickness 作為目標，測試 Weibull 迴歸

4. **驗證分析**
   - 點擊「執行完整驗證」
   - 查看模型比較表（R²/RMSE/AUC/shape_k/AIC）
   - 查看交互作用熱圖
   - 查看實驗建議

### 預期結果

- DOE 二次模型在連續輸出上應表現良好（資料含線性效應）
- Logistic 迴歸在 result 上的 AUC 應可接受（NG 比例約 2%）
- Weibull 迴歸可估計平均失效時間

### 進階測試

- 嘗試互動預測：調整 input_temperature=95，查看 output_thickness 預測值
- 嘗試蒙地卡羅模擬：選擇已配適模型，執行 10000 次模擬
- 嘗試 SPC 分析：選擇 input_temperature 或 output_thickness，查看管制圖與離群值
