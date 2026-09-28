# 部署指南

本專案是 Tauri 桌面應用程式，前端會啟動隨附的 Python 分析引擎。Python 套件由 `uv` 管理；PDF 匯出另需 WeasyPrint 的作業系統圖形與文字函式庫。

## 共通建置流程

開發環境（`npm run tauri dev`）直接使用 `engine/.venv`：

```bash
npm install
cd engine
uv venv --python 3.12
uv sync --extra dev
cd ..
npm run tauri dev
```

**發行建置必須先把引擎凍結成獨立執行檔再打包**，否則安裝後的 App 沒有 Python 可用，分析引擎無法啟動：

```bash
npm install
npm run engine:build     # PyInstaller -> src-tauri/resources/engine/
npm run tauri build
```

`npm run build:app` 等同上面兩行。`scripts/build-engine.mjs` 會建立引擎 venv、安裝相依套件、以 PyInstaller 產生 `src-tauri/resources/engine/process-intelligence-engine[.exe]`，並在結尾對凍結後的執行檔送出 `engine/ping` 煙霧測試。Tauri 透過 `tauri.conf.json` 的 `bundle.resources` 將 `src-tauri/resources/engine/` 複製到 `$RESOURCE/engine/`。

在各目標作業系統原生 runner 上建置；不要把 macOS 的 venv 或系統函式庫複製到 Windows 或 Linux 產物中。

### 引擎解析順序

執行時 `src-tauri/src/engine/mod.rs` 依序尋找，第一個存在者勝出：

1. `PROCESS_INTELLIGENCE_ENGINE` 環境變數（除錯／支援用；值為 Python 直譯器時以 `-m process_intelligence_engine.main` 執行）
2. `$RESOURCE/engine/process-intelligence-engine[.exe]`（發行版預設）
3. `$RESOURCE/engine/venv/…`（若改為隨附 venv 而非凍結執行檔）
4. 開發檢查區的 `engine/.venv/…`

全部落空時，啟動錯誤會列出所有嘗試過的路徑，而不是只回一句籠統的啟動失敗。

### 深度學習模型（TFT）

`--with-dl` 會一併打包 torch / pytorch-forecasting / lightning（產物大幅變大）；`--with-tensorflow` 另外加入 tensorflow。預設兩者皆排除：引擎以 `importlib.util.find_spec` 偵測不到時會自動退回既有模型，TFT 相關功能停用，其餘功能不受影響。

```bash
npm run engine:build -- --with-dl
```

### PyInstaller 無法跨平台／跨架構編譯

凍結後的引擎架構跟隨建置 runner。macOS x86_64 因此使用 Intel runner（`macos-13`）；CI 另有一道 `lipo -archs` 檢查，引擎架構與 bundle 目標不符時直接讓建置失敗，避免悄悄出貨無法執行的產物。

## v0.6.0 多層級資料範本

既有 CSV 可維持 `input_*`、`output_*` 與 `result` 欄位直接匯入；工程多層級範本則在相同輸入／輸出欄位之外，加入 `measurement_id`、`product_id`、`lot_id`、`machine_id`、`station_id`、`process_step` 與 `subgroup_id` 追溯欄位。這些欄位是可選的，不會破壞舊版 CSV。

時間欄位建議使用 `YYYY-MM-DD HH:MM:SS`（例如 `2026-09-09 08:00:00`）；引擎同時相容 ISO 8601 的 `T` 分隔符與時區格式。匯入後欄位角色會自動偵測，工程 ID 會標示為識別欄位，`part`／`product` 會標示為類別資料。

SPC 頁面的圖表類型、輸出欄位、子群組大小與 grain/filter 選擇會保存於專案檔，重開同一專案時自動恢復。

## PDF 報告匯出（WeasyPrint）

專案 venv 已安裝 Python `weasyprint` 套件，但它仍須載入 Pango、GObject 與字型相關的系統函式庫。以下指令供建置機與執行 PDF 匯出的工作站使用。詳細的發行版版本需求請以 [WeasyPrint 官方安裝文件](https://doc.courtbouillon.org/weasyprint/latest/first_steps.html) 為準。

### macOS

```bash
brew install weasyprint libomp
cd engine
uv sync --extra dev
DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_FALLBACK_LIBRARY_PATH}" \
  .venv/bin/python -m pytest tests/test_reporting.py -q
```

Apple Silicon 的 Homebrew library path 是 `/opt/homebrew/lib`；Intel Homebrew 通常是 `/usr/local/lib`。桌面應用程式啟動 Python 引擎時會自動加入偵測到的其中一個路徑，因此使用者不必設定 shell 環境變數。環境變數只用於命令列驗證。

### Ubuntu / Debian

```bash
sudo apt-get update
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0
cd engine
uv sync --extra dev
.venv/bin/python -m pytest tests/test_reporting.py -q
```

### Fedora

```bash
sudo dnf install -y pango
cd engine
uv sync --extra dev
.venv/bin/python -m pytest tests/test_reporting.py -q
```

### Windows

本專案的 Python 引擎需使用 Pango DLL，不能只安裝 WeasyPrint CLI executable。以 MSYS2 UCRT64 shell 安裝：

```powershell
pacman -S mingw-w64-ucrt-x86_64-pango
$env:WEASYPRINT_DLL_DIRECTORIES = 'C:\msys64\ucrt64\bin'
cd engine
uv sync --extra dev
.venv\Scripts\python -m pytest tests\test_reporting.py -q
```

將 `WEASYPRINT_DLL_DIRECTORIES` 設為實際包含 Pango DLL 的目錄，並在 CI 與打包工作流程中設定；部署到不同位置時不可假設固定磁碟機代號。

## 驗收

## AI 助手（v0.6.0）

預設使用本機 Ollama；若 Ollama 或選定模型未就緒，助手只顯示設定引導，不會自動切換至雲端。啟動 Ollama 後，在「系統設定」指定本機位址與模型，並以「測試連線」確認狀態。

雲端模型必須由使用者明確啟用。每個專案第一次傳送前，助手會顯示去敏預覽、遮罩欄位、數值政策與內容雜湊；數值預設保留原值，識別／企業識別欄位會遮罩。使用者必須確認專案層級傳送同意，且可在專案設定中撤銷。未完成預覽或同意時不會傳送資料。

助手只能提出解釋、下一步建議與操作草案。任何建立分析、驗證實驗或報告的寫入動作都必須逐次確認，並由既有版本鏈與稽核流程執行。

每個目標平台至少執行：

```bash
cd engine
.venv/bin/python -m pytest tests/test_reporting.py -q
```

Windows 請改用 `.venv\Scripts\python`。測試全部通過後，再於 Tauri App 產生一份 PDF 報告並以系統 PDF 閱讀器開啟。

### 專案目錄中的模型與模擬目錄

`models/` 與 `simulations/` 是預留的資產目錄，目前可保持空白。模型版本與模擬紀錄的實際索引、追溯與重建來源是 `registry/version_chain.jsonl`；模型與模擬完成後不會自動在這兩個目錄產生檔案。

## Vendored 依賴：`vendor/xlsx-0.20.3.tgz`

前端匯入／匯出 Excel 使用 SheetJS，而 **npm registry 上的 `xlsx` 停在 0.18.5，帶有未修補的 prototype pollution 與 ReDoS**（`npm audit` 對它回報 `No fix available`）。修好的版本只在 SheetJS 官方 CDN 發佈。

npm 12 起 `allow-remote` 預設為 `none`，會拒絕任何指向 tarball URL 的相依，因此**不能**在 `package.json` 直接寫 CDN 網址（會得到 `EALLOWREMOTE`）。`allow-file` 的預設仍為 `all`，所以改為隨 repo 附帶該 tarball，以 `file:` 引用：

```json
"xlsx": "file:vendor/xlsx-0.20.3.tgz"
```

`package-lock.json` 以 integrity 雜湊鎖定該檔，`npm ci` 會驗證。

**維護注意事項**

- `vendor/xlsx-0.20.3.tgz` **必須保留在版本控制中**，不要加入 `.gitignore`，也不要為了「乾淨」而刪除；刪掉會讓 `npm ci` 失敗。
- **不要**改回 CDN 網址，也**不要**用 `npm config set allow-remote all` 之類的全域放寬來繞過 —— 那等於對整個相依樹重新開放任意 tarball URL（npm 官方明列為不建議）。
- SheetJS 官方亦建議 vendoring（降低供應鏈攻擊面、可離線建置）。
- 升級時：抓取新版 tarball 放入 `vendor/`，更新 `package.json` 路徑後執行 `npm install`，並以 `npm ci --allow-remote=none` 驗證在硬化預設下仍可安裝。
