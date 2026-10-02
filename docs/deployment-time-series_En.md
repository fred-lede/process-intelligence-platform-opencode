# Time-Series Deep Model Deployment: TFT / PyTorch

This guide describes the Temporal Fusion Transformer (TFT) environment. TFT is integrated into the time-series ladder and can train/predict with PyTorch and Apple MPS; deployments without PyTorch can continue using existing models.

The engine checks for `pytorch_forecasting`, required columns, a default sequence length of 24, and at least 128 training sequences. When eligible, TFT is trained and included in the time-series model comparison; missing dependencies or insufficient history are reported explicitly. A fitted model must still pass the time-series validation gate; insufficient prediction-interval coverage is marked for review and cannot be persisted or used for formal simulation.

## Rules and installation order

Use Python 3.11 or 3.12, create a platform-local venv, install the project first, then the platform-specific PyTorch wheel, then `pytorch-forecasting`. Do not copy venvs between operating systems or CPU architectures. An isolated venv is optional because the tested PyTorch stack is included in requirements.

The examples use `engine/.venv-tft` so the application's normal `engine/.venv` remains unchanged.

## macOS: Apple Silicon and Intel CPU

```bash
cd engine
uv venv --python 3.12 .venv-tft
source .venv-tft/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install torch
python -m pip install pytorch-forecasting
python - <<'PY'
import torch, pytorch_forecasting
print("torch:", torch.__version__)
print("pytorch_forecasting:", pytorch_forecasting.__version__)
print("MPS:", torch.backends.mps.is_available())
print("CUDA:", torch.cuda.is_available())
PY
```

Apple Silicon may use MPS where available; Intel Macs normally use CPU. Neither should use CUDA wheels.

## Windows CPU

```powershell
cd engine
uv venv --python 3.12 .venv-tft
.\.venv-tft\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install torch
python -m pip install pytorch-forecasting
python -m pytest tests/test_time_series_models.py -k "tft or advanced_time_series_rows" -q
```

> **Note: `torch` installed from PyPI on Windows is CPU-only.** Since PyTorch 2.11, PyPI ships CUDA wheels only for Linux x86_64/aarch64; the default Windows wheel contains no CUDA and `torch.cuda.is_available()` returns `False`. To use a GPU on Windows, follow [Windows NVIDIA CUDA](#windows-nvidia-cuda) instead of `pip install torch`.

## Windows NVIDIA CUDA

Confirm the driver first:

```powershell
nvidia-smi --query-gpu=name,driver_version --format=csv
```

**The CUDA wheel version must match the GPU's compute capability:**

| GPU | Compute capability | Minimum usable wheel |
| --- | --- | --- |
| RTX 50 series (Blackwell, e.g. RTX 5090) | `sm_120` | **cu128 or newer** (cu118 is **not** supported) |
| RTX 40 series (Ada, e.g. RTX 4070 Ti) | `sm_89` | cu118 and up |
| RTX 30 series (Ampere) | `sm_86` | cu118 and up |

The `cu118` wheel tops out at Hopper (`sm_90`), so on a 50-series GPU it falls back to CPU or fails outright. `cu128` (from torch 2.7) and `cu130`/`cu132` support Blackwell natively. CUDA 13.x needs a newer driver (R580+); pick `cu128` if your driver is older.

In PowerShell:

```powershell
cd engine
uv venv --python 3.12 .venv-tft
.\.venv-tft\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

# Pick one of the following. uv must run inside the activated venv, otherwise add --python .venv-tft.
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu132
# uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu132

python -m pip install pytorch-forecasting
```

`torchvision` is not required by TFT (`pytorch-forecasting` never imports it) and can be omitted; it is kept here to match the official install command.

Verify (`CUDA: True` with capability `(12, 0)` means a 50-series GPU is correctly detected):

```powershell
python -c "import torch; print(torch.__version__, torch.version.cuda); print('CUDA:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))"
```

The `triton not found; flop counting will not work for triton kernels` warning on Windows is expected: Triton ships no Windows wheel and TFT does not use it.

With multiple GPUs present (e.g. RTX 5090 + RTX 4070 Ti), TFT should still work. If prediction fails with `unmatched '}' in format string`, Lightning selected DDP; the engine pins `predict()` to a single device to avoid this.

### Deploying the CUDA engine to a Windows install

The CUDA engine is **3.3 GB and cannot be packaged into an installer** — both MSI (WiX v3 fails cabinet creation) and NSIS (`makensis` is a 32-bit process) have a hard ~2 GB ceiling. Install the CPU build, then replace the engine directory. See [`deployment.md`](deployment.md#windows-gpu-部署先裝-cpu-版再替換引擎) for the full procedure (Windows-only, two-stage engine swap).

## Linux CPU

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

## Linux NVIDIA CUDA

Confirm the driver first with `nvidia-smi`. After creating the venv and installing the project, use the exact command generated by the [official PyTorch selector](https://pytorch.org/get-started/locally/) for the driver's compatible CUDA wheel. This is a CUDA 11.8 example only:

```bash
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
python -m pip install pytorch-forecasting
python - <<'PY'
import torch
print("CUDA:", torch.cuda.is_available())
if not torch.cuda.is_available():
    raise SystemExit("Select a wheel compatible with the installed NVIDIA driver.")
print(torch.cuda.get_device_name(0))
PY
```

## Capability check and fallback

```bash
python - <<'PY'
import importlib.util
print(importlib.util.find_spec("pytorch_forecasting") is not None)
PY
```

With the package installed, the Model Center reports the TFT dependency, data contract, sequence count, and execution device such as `pytorch/mps`. Without it, it reports `dependency_missing` without preventing engine startup. Lightning artifacts are written outside the Tauri source tree so training does not trigger a development restart.

If CUDA or MPS is unavailable, use CPU; do not force a CUDA wheel. If the optional environment fails, deactivate it and use the normal `engine/.venv` with the existing non-TFT models. TFT needs a time column, target, selected inputs, sequence length 24, and at least 128 usable training sequences.

References: [PyTorch Local Installation](https://pytorch.org/get-started/locally/) and [PyTorch Forecasting Installation](https://pytorch-forecasting.readthedocs.io/en/v1.8.0/installation.html).

## Sequence-aware simulation (Transformer)

This is the risk-use flow for a persisted Transformer, not independent Monte Carlo. The final risk gate must pass first: the model is `validated` or `approved`, reviewer/decision/reason provenance and approved time-series gate evidence exist, and the schema, backend, and framework version verify. Otherwise the endpoint returns `blocked/final_risk_gate_blocked`; do not bypass it.

`simulation_mode=sequence_aware` is a deterministic dry-run. Supply complete `history_rows` (time, target, and every input), future `input_scenarios` (time and inputs only; **never target**), and a `horizon` equal to the scenario count. Each step recursively uses historical targets and prior predictions with that step's scenario inputs; future targets are never used.

`simulation_mode=sequence_stochastic` additionally requires an integer `seed` and positive integer `n_simulations`. It uses the same recursive paths plus perturbations sampled from the historical recursive-residual scale, returning `mean`, `p05`, `p50`, `p95`, residual method, and provenance per step. Identical history, scenarios, seed, and model version produce reproducible summaries. This is model-risk estimation, not independent sampling or causal evidence.

Optional `observed_rows` are calibration evidence only after the forecasts exist. Each row needs time and target; the system aligns timestamps to the p05–p95 interval and returns step `covered` values and overall coverage. `nominal_confidence` is 0.90; `available` needs at least two aligned observations, `insufficient_observations` means fewer, and `not_available` means no post-hoc observations were supplied. It is not a future coverage guarantee and observed targets must never feed prediction.

In Model Center: select a persisted Transformer → paste history JSON and future-input-scenario JSON in Sequence-aware simulation → set horizon → choose deterministic or stochastic (then set paths and seed) → run. Review final-gate block reasons, backend/schema/version, path summaries, and calibration. `needs_sequence_simulation` means independent use is forbidden. Existing Monte Carlo/Copula time-series independent blocks remain in force.
