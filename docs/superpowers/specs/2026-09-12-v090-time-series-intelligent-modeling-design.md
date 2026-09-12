# v0.9.0 時間序列智慧建模設計

## 目標與核心流程

保留所有既有 DOE、統計、AI、混合模型與模擬功能，新增以大量歷史時間序列資料為主的建模模式：歷史資料匯入 → 時間排序與資料健檢 → 自動建立時間特徵 → 統計基準模型 → AI 非線性模型 → 混合模型比較 → SHAP／敏感度／交互作用解釋 → 時間外驗證 → 少量 DOE 或工程實驗確認 → 通過後才用於模擬與預測。

## 一、新增模型階梯

1. Naive／季節性 Naive：最簡單基準，確認複雜模型確實有增益。
2. ARIMA／SARIMA 或 State Space：處理單一輸出的趨勢、週期與自相關。
3. Dynamic Regression：使用多個 input、lag、rolling 與外部因素預測 output。
4. LightGBM／XGBoost 時間特徵模型：處理非線性、交互作用與大量表格型製程資料。
5. Residual Hybrid：統計模型處理趨勢與自相關，AI 模型處理殘差。
6. LSTM／Transformer／TFT：資料量、序列長度與驗證結果足夠時才啟用的進階模型。

## 二、資料與特徵處理

自動依時間欄位排序，檢查重複時間、缺值、不規則間隔、時區與斷點；依資料頻率建議並允許調整 `lag_1`、`lag_7`、`lag_24` 等 lag，以及 rolling mean、rolling std、差分、變化率、小時、班別、星期、批次與機台特徵。特徵只可使用當下可取得的歷史資料，並記錄來源、窗口、可用範圍與 data leakage 檢查結果。

## 三、驗證方式

時間序列不可只使用隨機 K-Fold；必須支援時間切分 train／validation／test、walk-forward validation、rolling-origin evaluation、依批次／機台／產品分層驗證、預測區間與不確定性評估，以及近期與長期資料窗口比較。預設窗口為 7 天快速基準、30 天一般建模、60／90 天穩健建模，並以後續 7–14 天作時間外驗證。

## 四、模型中心呈現方式

新增「時間序列智慧建模」頁籤或模式選擇，不改變現有模型中心操作。模型比較表增加模型類型、時間特徵、自相關處理、顯式交互作用、驗證方式、MAE／RMSE／R²、預測區間覆蓋率、外推風險、資料洩漏檢查、模型版本與訓練時間範圍。使用說明同步增加操作步驟、統計原理、限制與工程建議。

## 五、現有功能定位

- DOE 線性：主效應基準模型。
- DOE 二次：曲率與顯式交互作用模型。
- Random Forest／XGBoost／LightGBM：非線性 AI 模型。
- Residual Hybrid：統計＋AI 混合模型。
- ARIMA／State Space：時間序列統計基準。
- LSTM／Transformer／TFT：進階時間序列模型。
- DOE 實驗：少量因果確認與最終工程驗證。
- Monte Carlo／Copula：使用通過驗證的模型與輸入分布進行風險模擬。

## 六、開發階段

### Phase 1：時間序列基礎

- 時間排序、品質檢查、時間窗口。
- 時間切分驗證。
- lag／rolling／差分特徵。
- Naive、ARIMA／State Space、Dynamic Regression。

### Phase 2：AI 與混合模型

- 時間特徵版 LightGBM／XGBoost。
- 時間序列 Residual Hybrid。
- SHAP、敏感度與交互作用支援。

### Phase 3：進階深度學習

- LSTM、Transformer、Temporal Fusion Transformer。
- 預測區間與模型不確定性。

### Phase 4：工程閉環

- 少量 DOE 實驗設計。
- 實測結果回填。
- 模型再訓練與版本比較。
- 通過 Gate 後才能用於 Monte Carlo、Copula 與正式報告。

## 相容性、驗收與最終定位

既有 CSV／工程多層級資料契約、model registry、Monte Carlo、Copula、SHAP、敏感度、交互作用、報告與 Gate 流程維持相容。既有模型與測試流程必須保持通過；時間序列不可只用隨機切分；相同資料窗口、特徵設定與模型版本必須可重現；UI 必須區分基準、時間序列、AI 與 DOE 驗證用途。平台以大量歷史時間序列資料為主要建模來源，統計與 AI 並行比較，混合模型提升預測能力，最後以少量 DOE 驗證關鍵結論。
