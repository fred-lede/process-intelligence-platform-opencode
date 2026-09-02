# 預存測試資料說明

## 檔案：data/test_dataset.csv

### 欄位說明
| 欄位 | 名稱 | 類型 | 範圍 | 說明 |
|------|------|------|------|------|
| temperature | 溫度 | 輸入 | 150-225°C | 製程溫度 |
| pressure | 壓力 | 輸入 | 10-20 MPa | 製程壓力 |
| time | 時間 | 輸入 | 30-60 min | 處理時間 |
| humidity | 濕度 | 輸入 | 45-60% | 環境濕度 |
| yield | 產率 | 輸出 | 78-94% | 製程產率 |

### 資料特性
- **樣本數**：77 筆
- **輸入變數**：4 個（temperature, pressure, time, humidity）
- **輸出變數**：1 個（yield）
- **關係**：包含線性效應 + 交互作用（temperature × pressure）

### 建議測試流程

1. **匯入資料**
   - 開啟「資料匯入」TAB
   - 上傳 `data/test_dataset.csv`
   - 系統自動辨識：temperature/pressure/time/humidity 為 input，yield 為 output

2. **製程定義**
   - 開啟「製程定義」TAB
   - 設定 yield 規格：LSL=80, USL=95
   - 可開啟自動 3σ 管制線

3. **模型配適**
   - 開啟「模型中心」TAB
   - 測試三種模型：
     - DOE 線性
     - DOE 二次
     - 隨機樹
     - 殘差混合

4. **驗證分析**
   - 點擊「執行完整驗證」
   - 查看模型比較表
   - 查看交互作用熱圖（temperature × pressure 應最顯著）
   - 查看實驗建議

### 預期結果
- DOE 二次模型應表現最佳（因為資料包含交互作用）
- temperature × pressure 交互作用應顯著
- 殘差應大致常態（Durbin-Watson ≈ 2.0）

### 進階測試
- 嘗試外插：在模型中心輸入 temperature=250（超出訓練範圍 150-225）
- 查看外插風險評分是否變高