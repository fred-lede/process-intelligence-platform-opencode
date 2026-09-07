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

每個目標平台至少執行：

```bash
cd engine
.venv/bin/python -m pytest tests/test_reporting.py -q
```

Windows 請改用 `.venv\Scripts\python`。測試全部通過後，再於 Tauri App 產生一份 PDF 報告並以系統 PDF 閱讀器開啟。
