# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Process Intelligence analysis engine.

Build it through ``scripts/build-engine.mjs`` rather than calling PyInstaller
directly; that script sets the environment flags below and copies the result
into ``src-tauri/resources/engine/`` so the Tauri bundler picks it up.

Environment flags
-----------------
PIE_WITH_DL=1
    Include the optional deep-learning stack (torch, pytorch-forecasting,
    lightning). Off by default: the engine probes those packages with
    ``importlib.util.find_spec`` and degrades gracefully when they are
    absent (see modeling/time_series_models.py), so the base bundle keeps
    every non-DL feature at a fraction of the size.
PIE_WITH_TENSORFLOW=1
    Include tensorflow as well. Off by default for the same reason and
    because its PyInstaller hooks are the most fragile part of the stack.
"""

import glob
import importlib
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

with_dl = os.environ.get("PIE_WITH_DL", "0") == "1"
with_tensorflow = os.environ.get("PIE_WITH_TENSORFLOW", "0") == "1"

datas = []
binaries = []
hiddenimports = collect_submodules("process_intelligence_engine")

# Scientific / modelling stack. These ship data files and compiled extension
# modules that PyInstaller's static analysis alone does not always pick up
# (notably shap's numba/llvmlite codegen and lightgbm's shared library).

# A subpackage's __init__ must be importable for collect_submodules to walk it, and some
# of them are not importable on a build machine that has no test dependencies. The worst
# case is xgboost.testing, which calls pytest.importorskip("hypothesis") at import time:
# that raises pytest's Skipped, which derives from BaseException rather than Exception,
# so neither PyInstaller's `except ImportError` nor the bare `except Exception` below can
# swallow it. The single failing subpackage aborted the entire collect_all("xgboost") call,
# so xgboost/lib/xgboost.dll was never collected and the frozen engine died at runtime
# with XGBoostLibraryNotFound -- silently, because the exception was discarded. Test
# subpackages are dead weight in a frozen bundle, so skip them during collection.
def _is_not_test_submodule(name):
    return not any(part in ("testing", "tests") for part in name.split("."))


for package in (
    "xgboost",
    "lightgbm",
    "shap",
    "statsmodels",
    "sklearn",
    "scipy",
    "numba",
    "llvmlite",
    "gplearn",
    "pyDOE2",
    "weasyprint",
    "openpyxl",
    "joblib",
    "aiohttp",
):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(
            package, filter_submodules=_is_not_test_submodule
        )
    except Exception as exc:  # pragma: no cover - optional at build time
        # Never swallow this quietly. A package that fails to collect takes its compiled
        # libraries with it, and the engine then fails at runtime with something like
        # "Cannot find XGBoost Library" that points nowhere near the build.
        print(f"WARNING: collect_all({package!r}) failed, its libraries will be missing: {exc}")
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# torchvision has to ship its own compiled extension, and no automatic collection finds
# it. torchvision 0.29 loads it at runtime rather than importing it --
# torchvision/extension.py calls torch.ops.load_library(_get_extension_path("_C_stable")),
# which resolves relative to the package directory -- so PyInstaller's static analysis sees
# no import to follow. Its bundled hook is also stale: it still looks for torchvision._C,
# which 0.29 renamed to _C_stable, and collect_dynamic_libs only matches files whose name
# starts with the package name, so "_C_stable.pyd" is skipped too. The load swallows
# ImportError and OSError and returns False, so nothing fails at build time and nothing
# fails loudly at startup either; torchvision.ops.nms just raises "operator
# torchvision::nms does not exist", which takes out every TFT fit while leaving the rest
# of the ladder working.
#
# Everything below has to land in the same directory: on Windows _get_extension_path calls
# os.add_dll_directory() on it, so the sibling DLLs (_C_stable.pyd links against jpeg8,
# libpng16, nvjpeg64, libwebp, zlib and sharpyuv) must sit next to it.
if with_dl:
    try:
        torchvision_dir = os.path.dirname(importlib.import_module("torchvision").__file__)
    except ImportError:
        print("WARNING: torchvision is not installed; TFT will fail in the frozen engine")
    else:
        tv_datas, tv_binaries, tv_hidden = collect_all(
            "torchvision", filter_submodules=_is_not_test_submodule
        )
        datas += tv_datas
        binaries += tv_binaries
        hiddenimports += tv_hidden
        extensions = sorted(
            glob.glob(os.path.join(torchvision_dir, "*.pyd"))
            + glob.glob(os.path.join(torchvision_dir, "*.so"))
            + glob.glob(os.path.join(torchvision_dir, "*.dylib"))
        )
        if not extensions:
            print("WARNING: no torchvision extension module found; TFT will fail in the frozen engine")
        for extension in extensions:
            binaries.append((extension, "torchvision"))
            print(f"  collected torchvision extension {os.path.basename(extension)}")

    # torchgen: torch imports it eagerly from torch.utils._python_dispatch,
    # torch._library.utils and torch._custom_op.impl, all of which run during a plain
    # `import torch`. It is a top-level package, so nothing inside torch references it
    # by a path PyInstaller's torch hook can follow, and the hook does not collect it.
    # Without it every torch import dies at startup with
    #   ModuleNotFoundError: No module named 'torchgen'
    # which the device probe reports only as "cuda_available: false" -- the CUDA DLLs
    # are still on disk, so the DLL-based check passes and the failure looks like a
    # driver problem instead of a packaging one.
    try:
        import torchgen  # noqa: F401
    except ImportError:
        print("WARNING: torchgen is not installed; every torch import will fail in the frozen engine")
    else:
        gen_datas, gen_binaries, gen_hidden = collect_all(
            "torchgen", filter_submodules=_is_not_test_submodule
        )
        datas += gen_datas
        binaries += gen_binaries
        hiddenimports += gen_hidden
        print(f"  collected torchgen ({len(gen_hidden)} hidden imports)")

# HarfBuzz-Subset: WeasyPrint 70 warns that it "will be required by future versions"
# for font subsetting. It is loaded at runtime, is not a dependency of any library
# collected above, and so nothing pulls it in transitively -- which is why it is
# missing from the bundle today. Added explicitly, and its absence is reported rather
# than ignored, so a build never silently produces a PDF-incapable engine.
#
#   Linux:  sudo apt-get install -y libharfbuzz-subset0
#   macOS:  brew install harfbuzz          (ships libharfbuzz-subset*.dylib)
import glob
import sys

_subset_patterns = []
if sys.platform.startswith("linux"):
    _subset_patterns = ["/usr/lib/*/libharfbuzz-subset.so*", "/usr/lib/libharfbuzz-subset.so*"]
elif sys.platform == "darwin":
    _subset_patterns = [
        "/opt/homebrew/lib/libharfbuzz-subset*.dylib",
        "/usr/local/lib/libharfbuzz-subset*.dylib",
    ]

_subset_seen = set()
for _pattern in _subset_patterns:
    for _path in glob.glob(_pattern):
        _real = os.path.realpath(_path)
        if _real in _subset_seen:
            continue
        _subset_seen.add(_real)
        binaries.append((_real, "."))

if _subset_seen:
    print(f"harfbuzz-subset: bundling {len(_subset_seen)} file(s)")
else:
    print(
        "WARNING: libharfbuzz-subset not found -- PDF font subsetting will break once "
        "WeasyPrint requires it. Install libharfbuzz-subset0 (Linux) or harfbuzz via "
        "Homebrew (macOS) on this build machine and rebuild."
    )

# CUDA runtime libraries that xgboost pulls in on Linux (`nvidia-nccl-cu12`
# and friends). They account for roughly 450 MB -- about a third of the whole
# bundle -- and the GPU path is opt-in, off by default, and additionally needs
# a system CUDA toolkit and an NVIDIA GPU. Shipping them by default is not a
# good trade; build with PIE_WITH_CUDA=1 if a GPU deployment needs them.
if os.environ.get("PIE_WITH_CUDA", "0") != "1":
    binaries = [b for b in binaries if "/nvidia/" not in b[0].replace("\\", "/")]
    datas = [d for d in datas if "/nvidia/" not in d[0].replace("\\", "/")]

excludes = [
    "tkinter",
    "matplotlib",
    "IPython",
    "notebook",
    "pytest",
    "pytest_cov",
    "coverage",
]

if os.environ.get("PIE_WITH_CUDA", "0") != "1":
    excludes += ["nvidia"]

if not with_dl:
    excludes += ["torch", "pytorch_forecasting", "lightning", "pytorch_lightning"]
if not with_tensorflow:
    excludes += ["tensorflow", "keras", "tensorboard"]

analysis = Analysis(
    [os.path.join(SPECPATH, "engine_entry.py")],
    pathex=[os.path.join(SPECPATH, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="process-intelligence-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="process-intelligence-engine",
)
