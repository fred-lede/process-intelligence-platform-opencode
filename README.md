# Process Intelligence Platform

**作者**: Fred Wang

可解釋、可追溯、可切換模型的製程分析平台。支援 macOS / Windows 桌面應用，結合傳統 DOE 與 AI 輔助分析。

## GitHub

[fred-lede/process-intelligence-platform-opencode](https://github.com/fred-lede/process-intelligence-platform-opencode)

## License

[MIT License](LICENSE) — Copyright (c) 2026 Fred Wang

## 技術架構

- **前端**: React 18 + TypeScript + Ant Design 5 + Zustand + i18next
- **桌面框架**: Tauri 2.0 (Rust)
- **分析引擎**: Python 3.11+ (numpy, pandas, scikit-learn, scipy, shap)
- **圖表庫**: Plotly.js
- **資料儲存**: 記憶體 DatasetRegistry (原始資料不上雲)

## 快速開始

### 前置需求

- Rust 1.77+（[安裝指南](https://www.rust-lang.org/tools/install)）
- Node.js 18+
- Python 3.11+
- 系統 WebView (macOS: WebKit / Windows: WebView2)

### 安裝 Rust（若尚未安裝）

```bash
# macOS / Linux
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Windows
# 下載並執行 https://win.rustup.rs/x86_64
# 或從 Microsoft Store 安裝 Rust
```

安裝後重啟終端機，或執行：

```bash
source $HOME/.cargo/env
```

確認安裝成功：

```bash
cargo --version
# 應輸出：cargo 1.xx.x
```

### 安裝與開發

```bash
# 安裝前端依賴
npm install

# 建立 Python 虛擬環境（仅需第一次）
cd engine
python3 -m venv .venv
# On Windows:
# .venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate
pip install -e ".[dev]"
cd ..

# 確認 Rust 環境
source $HOME/.cargo/env 2>/dev/null || true
cargo --version

# 啟動開發環境
npm run tauri dev

### 首次部署注意事項

在新電腦上首次部署時，請確保：

1. **Rust 已安裝**：執行 `cargo --version` 確認
2. **Python venv 已建立**：執行 `cd engine && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
3. **Node 模組已安裝**：執行 `npm install`
4. **瀏覽器 WebView**：macOS 內建 WebKit，Windows 需安裝 WebView2 Runtime

若啟動時出現 `failed to run cargo metadata` 錯誤，表示 Rust 未正確安裝或 PATH 未設定。
