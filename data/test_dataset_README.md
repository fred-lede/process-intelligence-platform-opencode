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

- **樣本數**：60 筆
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

- DOE 線性與 DOE 二次模型可直接比較；新增資料含受控的曲率訊號，二次模型應能捕捉非線性，兩者模擬結果不必完全相同
- 增加樣本後，模型係數與模擬百分位數應較 45 筆基準穩定
- Logistic 迴歸在 result 上的 AUC 應可接受（NG 比例約 2%）
- Weibull 迴歸可估計平均失效時間

### 進階測試

- 嘗試互動預測：調整 input_temperature=95，查看 output_thickness 預測值
- 嘗試蒙地卡羅模擬：選擇已配適模型，執行 10000 次模擬
- 嘗試 SPC 分析：選擇 input_temperature 或 output_thickness，查看管制圖與離群值

## 情境測試資料

以下檔案是程式測試用 fixture，不是資料匯入頁提供給使用者下載的收集範本。一般情境沿用一般 CSV 的 13 欄結構；GRR 使用工程多層級結構。

| 檔案 | 資料特性 | 主要驗證功能 | 使用方式 |
|------|----------|--------------|----------|
| `test_dataset.csv` | 60 筆綜合基準資料 | 匯入、健檢、製程定義、一般模型與報告 | 依本文件完整流程匯入 |
| `test_dataset_linear.csv` | 10 筆，輸出近似線性組合 | DOE 線性、互動預測 | 配適 DOE 線性並檢查係數 |
| `test_dataset_quadratic.csv` | 10 筆，輸出含曲率 | DOE 二次、模型比較 | 同時配適線性與二次 |
| `test_dataset_interaction.csv` | 10 筆，輸出含交互作用 | 交互作用、SHAP、敏感度與效應量 | 配適後檢查交互作用與排名 |
| `test_dataset_quality_issues.csv` | 8 筆，含缺值、重複、錯序與格式差異 | 資料品質報告與 readiness | 匯入後先檢查 warning |
| `test_dataset_grr.csv` | 工程欄位，含零件、操作者與重複量測 | GRR | 指定測量、零件與操作者欄位 |
| `test_dataset_timeseries.csv` | 12 筆有序時間與週期變化 | 趨勢、時間序列、SPC | 指定 `datetime` 與數值欄位 |
| `test_dataset_out_of_spec.csv` | 8 筆，輸出跨越 LSL／USL | SPC、規格判定、蒙地卡羅 NG 風險 | 設定規格後檢查超限 |

### 測試注意事項

- 情境檔案供快速驗證功能；正式統計結論仍需足量且具代表性的資料。
- DOE 情境使用相同核心欄位，但輸出關係不同，因此模型與模擬結果應有可解釋差異。
- 比較模型或蒙地卡羅情境時，固定規格、模擬次數與隨機種子。
- `test_dataset_quality_issues.csv` 的問題是刻意設計，預期由資料品質檢查偵測。
- `test_dataset_grr.csv` 使用工程多層級欄位，不能直接套用一般 CSV 的欄位角色假設。
