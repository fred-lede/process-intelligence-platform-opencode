# 部署指南

本專案是 Tauri 桌面應用程式，前端會啟動隨附的 Python 分析引擎。Python 套件由 `uv` 管理；PDF 匯出另需 WeasyPrint 的作業系統圖形與文字函式庫。

## 共通建置流程

```bash
npm install
cd engine
uv venv --python 3.12
uv sync --extra dev
cd ..
npm run tauri build
```

在各目標作業系統原生 runner 上建置；不要把 macOS 的 venv 或系統函式庫複製到 Windows 或 Linux 產物中。

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
