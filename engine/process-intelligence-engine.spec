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
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    except Exception:  # pragma: no cover - optional at build time
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

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
