# 時間序列深度模型部署：TFT / PyTorch（選配）

本文件說明 Temporal Fusion Transformer（TFT）的**選配**執行環境。它不會修改本專案的 base requirements，也不會使沒有 PyTorch 的一般桌面部署失效。

目前引擎會檢查 `pytorch_forecasting`、資料欄位、sequence length（預設 24）與至少 128 個訓練序列；即使依賴與資料都符合，TFT 仍會標示為 `not_implemented`，不會開始訓練。這個獨立環境是為後續 TFT 實作與驗證預先準備的。

## 共通原則與安裝順序

1. 使用 Python 3.11 或 3.12；不要共用或複製不同 OS/CPU 架構的 venv。
2. 先建立本專案與開發測試環境，再安裝**目標平台對應的 PyTorch**，最後安裝 `pytorch-forecasting`。
3. NVIDIA CUDA wheel 必須依 [PyTorch 官方 selector](https://pytorch.org/get-started/locally/) 選擇，不能把其他主機的 CUDA wheel 複製過來。
4. 不要把 `torch`、`pytorch-forecasting`、`pytorch-lightning` 加入 `engine/pyproject.toml` 或 base requirements；這些只屬於選配 TFT venv。

以下示例把環境命名為 `.venv-tft`，避免影響桌面應用程式預設使用的 `engine/.venv`。

## macOS（Apple Silicon 與 Intel CPU）

Apple Silicon 與 Intel 都使用 macOS CPU/MPS wheel；TFT 的部署驗證不應假設 CUDA。於專案根目錄執行：

```bash
cd engine
uv venv --python 3.12 .venv-tft
source .venv-tft/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install torch
python -m pip install pytorch-forecasting
```

Apple Silicon 可額外檢查 MPS；Intel 通常會是 `False`，仍可用 CPU：

```bash
python - <<'PY'
import torch
import pytorch_forecasting
print("torch:", torch.__version__)
print("pytorch_forecasting:", pytorch_forecasting.__version__)
print("MPS available:", torch.backends.mps.is_available())
print("CUDA available:", torch.cuda.is_available())
PY
```

## Windows（CPU）

在 PowerShell 中：

```powershell
cd engine
uv venv --python 3.12 .venv-tft
.\.venv-tft\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install torch
python -m pip install pytorch-forecasting
```

驗證：

```powershell
python -c "import torch, pytorch_forecasting; print(torch.__version__); print('CUDA:', torch.cuda.is_available()); print(pytorch_forecasting.__version__)"
python -m pytest tests/test_time_series_models.py -k "tft or advanced_time_series_rows" -q
```

## Linux（CPU）

```bash
cd engine
uv venv --python 3.12 .venv-tft
source .venv-tft/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install torch
python -m pip install pytorch-forecasting
python -m pytest tests/test_time_series_models.py -k 'tft or advanced_time_series_rows' -q
```

## Linux（NVIDIA CUDA）

先確認 NVIDIA driver 可用：

```bash
nvidia-smi
```

建立 venv 與專案依賴後，使用 PyTorch selector 提供且符合此主機 driver/CUDA 的命令。下列是 **CUDA 11.8 wheel 的示例**，不是固定版本承諾：

```bash
cd engine
uv venv --python 3.12 .venv-tft
source .venv-tft/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

# 以 PyTorch selector 為準；此行僅為 cu118 範例。
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
python -m pip install pytorch-forecasting
```

驗證 CUDA 與套件：

```bash
python - <<'PY'
import torch
import pytorch_forecasting
print("torch:", torch.__version__)
print("pytorch_forecasting:", pytorch_forecasting.__version__)
print("CUDA available:", torch.cuda.is_available())
if not torch.cuda.is_available():
    raise SystemExit("CUDA is unavailable: return to the PyTorch selector and match driver/wheel.")
print("GPU:", torch.cuda.get_device_name(0))
PY
python -m pytest tests/test_time_series_models.py -k 'tft or advanced_time_series_rows' -q
```

## 引擎 capability 驗證

無論平台，從 `engine/` 內執行：

```bash
python - <<'PY'
import importlib.util
print("pytorch_forecasting available:", importlib.util.find_spec("pytorch_forecasting") is not None)
PY
```

安裝成功後，Model Center 的 TFT capability 應顯示依賴可用、資料 contract、sequence length 與可用序列數；符合至少 128 組訓練序列時會執行 TFT 訓練並列入比較。資料不足或缺少套件時，應明確顯示 `insufficient_history` 或 `dependency_missing`，不是引擎啟動失敗。

## Fallback 與排錯

- **一般使用／CPU 不足／CUDA 不可用：** 不啟用 `.venv-tft`，繼續使用 `engine/.venv` 與現有 Naive、ARIMA、Dynamic Regression、樹模型或 Transformer（TensorFlow）流程。
- **`torch.cuda.is_available()` 為 `False`：** 不要強制設定 CUDA；改用 Linux CPU 指令，或依官方 selector 換成與 driver 相容的 wheel。
- **macOS 顯示 MPS 不可用：** 使用 CPU，勿嘗試 CUDA wheel。
- **`No module named pytorch_forecasting`：** 確認已 activate `.venv-tft`，且安裝順序為 `torch` 後 `pytorch-forecasting`。
- **資料不符合門檻：** 保持傳統/既有模型；TFT 需要時間欄、target、已選 inputs、sequence length 24，且訓練區至少 128 個可用序列。

官方參考：[PyTorch Local Installation](https://pytorch.org/get-started/locally/)；[PyTorch Forecasting Installation](https://pytorch-forecasting.readthedocs.io/en/v1.8.0/installation.html)。

## Sequence-aware simulation（Transformer）

這是已持久化 Transformer 的風險使用流程，與獨立 Monte Carlo 不同。使用前必須通過 final risk gate：模型狀態為 `validated` 或 `approved`、具備 reviewer/decision/reason、已核准的 time-series gate evidence，以及可驗證的 schema、backend 與 framework version。未通過時 endpoint 回傳 `blocked/final_risk_gate_blocked`；不得繞過 gate。

`simulation_mode=sequence_aware` 是 deterministic dry-run：提供完整 `history_rows`（時間、target、所有 inputs）與未來 `input_scenarios`（時間與 inputs，**不得含 target**），並指定等於 scenario 數的 `horizon`。每一步以歷史 target 與先前預測遞迴，使用該步的情境 input；不會使用未來 target。

`simulation_mode=sequence_stochastic` 另外需要整數 `seed` 與正整數 `n_simulations`。它以相同的遞迴序列預測，加上從歷史遞迴殘差尺度產生的路徑擾動，回傳每個時間點的 `mean`、`p05`、`p50`、`p95`、殘差方法與 provenance。相同 history、scenario、seed 與版本應產生可重現的摘要；這是模型風險估計，不是獨立抽樣或因果結論。

可選的 `observed_rows` 只能在預測完成後用於校正：每列需含時間與 target，系統以時間對齊 p05–p95 區間，回傳逐步 `covered` 與 overall coverage。`nominal_confidence` 為 0.90；`available` 表示至少兩個對齊觀測，`insufficient_observations` 表示觀測不足，`not_available` 表示尚未提供事後觀測。這不是未來覆蓋率保證，也不能把 observed target 回餵產生預測。

Model Center 操作：選擇已持久化 Transformer → 在 Sequence-aware simulation 卡貼入 history JSON 與 future input scenarios JSON → 設定 horizon → 選 deterministic 或 stochastic（後者設定 paths 與 seed）→ 執行。查看 final-gate blocked 原因、backend/schema/version、路徑摘要與 calibration；若顯示 `needs_sequence_simulation`，代表 independent 模式不被允許。既有 Monte Carlo/Copula 對時間序列模型仍維持 independent block。
