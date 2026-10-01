# 時間序列深度模型部署：TFT / PyTorch

本文件說明 Temporal Fusion Transformer（TFT）的執行環境。TFT 已接入時間序列模型階梯，並可使用 PyTorch／Apple MPS 訓練與預測；沒有 PyTorch 時仍可使用既有模型。

目前引擎會檢查 `pytorch_forecasting`、資料欄位、sequence length（預設 24）與至少 128 個訓練序列；符合條件時執行 TFT 訓練，否則明確回報缺少依賴或資料不足。配適完成後仍須執行時間序列驗證閘門；預測區間覆蓋率不足時會標示「需要審查」，不可直接保存或用於正式模擬。

## 共通原則與安裝順序

1. 使用 Python 3.11 或 3.12；不要共用或複製不同 OS/CPU 架構的 venv。
2. 先建立本專案與開發測試環境，再安裝**目標平台對應的 PyTorch**，最後安裝 `pytorch-forecasting`。
3. NVIDIA CUDA wheel 必須依 [PyTorch 官方 selector](https://pytorch.org/get-started/locally/) 選擇，不能把其他主機的 CUDA wheel 複製過來。
4. 可直接使用專案 `engine/.venv`；若要隔離環境，才建立獨立 `.venv-tft`。

以下示例把環境命名為 `.venv-tft`，也可替換成既有 `engine/.venv`。

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

> **注意：Windows 上從 PyPI 裝的 `torch` 是 CPU-only。** 自 PyTorch 2.11 起，PyPI 只為 Linux x86_64／aarch64 提供 CUDA wheel，Windows 的 PyPI 預設 wheel 不含 CUDA，`torch.cuda.is_available()` 會是 `False`。要在 Windows 使用 GPU，請改用下方〈Windows（NVIDIA CUDA）〉，不要用本節的 `pip install torch`。

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

## Windows（NVIDIA CUDA）

先確認驅動程式：

```powershell
nvidia-smi --query-gpu=name,driver_version --format=csv
```

**選擇 CUDA wheel 版本時，必須先確認 GPU 的 compute capability：**

| 顯示卡 | compute capability | 最低可用 wheel |
| --- | --- | --- |
| RTX 50 系列（Blackwell，例如 RTX 5090） | `sm_120` | **cu128 或更新**（cu118 **不支援**） |
| RTX 40 系列（Ada，例如 RTX 4070 Ti） | `sm_89` | cu118 起即可 |
| RTX 30 系列（Ampere） | `sm_86` | cu118 起即可 |

`cu118` 的 wheel 最高只到 Hopper（`sm_90`），在 50 系列上會退回 CPU 或直接失敗。`cu128`（自 torch 2.7 起）與 `cu130`／`cu132` 都原生支援 Blackwell。CUDA 13.x 需要較新的驅動程式（R580 以上）；若驅動程式較舊，請選 `cu128`。

在 PowerShell 中：

```powershell
cd engine
uv venv --python 3.12 .venv-tft
.\.venv-tft\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

# 兩種安裝方式擇一。uv 必須在已 activate 的 venv 中執行，否則要加 --python .venv-tft。
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu132
# uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu132

python -m pip install pytorch-forecasting
```

`torchvision` 並非 TFT 所需（`pytorch-forecasting` 不會 import 它），可省略；保留是為了與官方安裝指令一致。

驗證（`torch.cuda` 為 `True` 且 capability 為 `(12, 0)` 代表 50 系列已被正確辨識）：

```powershell
python -c "import torch; print(torch.__version__, torch.version.cuda); print('CUDA:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))"
```

若在 Windows 看到 `triton not found; flop counting will not work for triton kernels` 警告，屬正常現象：Triton 不提供 Windows 輪廓，TFT 不使用它，可忽略。

多張 GPU 同時存在時（例如 RTX 5090 + RTX 4070 Ti），TFT 仍應正確運作。預測階段若出現 `unmatched '}' in format string`，代表 Lightning 選用了 DDP；引擎已將 `predict()` 的 trainer 固定為單一裝置以避免此問題。

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

建立 venv 與專案依賴後，使用 PyTorch selector 提供且符合此主機 driver/CUDA 的命令。**wheel 版本必須符合顯示卡的 compute capability**（對照表見上方〈Windows（NVIDIA CUDA）〉）：`cu118` 最高只到 Hopper（`sm_90`），**無法執行 Blackwell 50 系列的 `sm_120`**，需改用 `cu128`／`cu130`／`cu132`。下列是 **cu118 wheel 的示例**，不是固定版本承諾：

```bash
cd engine
uv venv --python 3.12 .venv-tft
source .venv-tft/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

# 以 PyTorch selector 為準；此行僅為 cu118 範例（Hopper 及以下適用）。
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

安裝成功後，Model Center 的 TFT capability 應顯示依賴可用、資料 contract、sequence length、可用序列數與運算裝置（例如 `pytorch/mps`）；符合至少 128 組訓練序列時會執行 TFT 訓練並列入比較。資料不足或缺少套件時，應明確顯示 `insufficient_history` 或 `dependency_missing`，不是引擎啟動失敗。Lightning 訓練產物會寫入系統暫存目錄，不應觸發 Tauri 開發程序重啟。

### 以 `system/device_probe` 確認加速器

設定頁的「測試 CUDA 可用性」會呼叫 `system/device_probe`，逐一回報驅動程式、此版本內含的 CUDA runtime、torch 與 booster 的 GPU 支援，並給出總結 `cuda_usable`。也可直接從 `engine/` 內執行：

```bash
python -c "import sys, json; sys.path.insert(0,'src'); from process_intelligence_engine import main; print(json.dumps(main._handle_device_probe({}), indent=2, default=str))"
```

`cuda_usable: true` 代表驅動程式、CUDA runtime 與 torch／booster 齊備。該探測**不會**實際執行 GPU 運算，通過只代表元件齊備，不代表配適一定能成功；它也不會掩蓋 `torch.cuda.is_available()` 為 `False` 的情況（此時 `torch` 欄位會附上原因）。

## Fallback 與排錯

- **一般使用／CPU 不足／CUDA 不可用：** 不啟用 `.venv-tft`，繼續使用 `engine/.venv` 與現有 Naive、ARIMA、Dynamic Regression、樹模型或 Transformer（TensorFlow）流程。
- **`torch.cuda.is_available()` 為 `False`：** 不要強制設定 CUDA；確認安裝的是 CPU wheel（Windows 上 `pip install torch` 即為此情形），改用對應平台的 CUDA wheel，或退回 CPU 指令。
- **Windows 顯示 `cuda_usable: false` 但 GPU 正常：** 確認 `torch/lib/` 內存在 `cudart*.dll`；此為 CUDA build 應具備的檔案。
- **預測階段出現 `unmatched '}' in format string`：** 主機有多張 GPU 時，Lightning 的 `predict()` 預設 `devices="auto"` 會選用 DDP，而 DDP 的環境變數 rendezvous 在 Windows 上失敗。將 `predict()` 的 trainer 固定為單一裝置即可。
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
