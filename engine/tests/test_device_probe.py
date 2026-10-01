"""Device probe: the engine-side answer to "can this build actually use CUDA?".

The probe exists because "cannot use CUDA" has several distinct causes -- no driver, a
CPU-only bundle, torch absent because the build ships no deep-learning stack -- and a
user who has just set the device to 'gpu' needs to know which one applies. It therefore
reports each piece separately plus one headline derived from them.
"""
import json
import shutil

from process_intelligence_engine.main import _handle_device_probe, _find_cuda_runtime_libraries


def test_probe_reports_every_piece_separately():
    """Each cause must be visible on its own; a single boolean hides the fix."""
    out = _handle_device_probe({})
    for key in ("nvidia_smi", "cuda_runtime_in_bundle", "torch", "xgboost_gpu", "lightgbm_gpu"):
        assert key in out, f"missing {key}: the failure would be unattributable"
    assert isinstance(out["cuda_usable"], bool)
    # It crosses the IPC boundary as JSON, so anything non-serializable would fail at
    # the frontend rather than here.
    json.dumps(out)


def test_headline_is_derived_from_the_items():
    """Guards against the summary drifting from the checks it summarizes."""
    out = _handle_device_probe({})
    expected = bool(
        out["nvidia_smi"].get("available")
        and out["cuda_runtime_in_bundle"].get("present")
        and (out["torch"].get("cuda_available") or out["xgboost_gpu"].get("supported"))
    )
    assert out["cuda_usable"] == expected


def test_missing_driver_is_reported_with_a_reason(monkeypatch):
    """Proves the probe reads the environment rather than returning a fixed answer."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    out = _handle_device_probe({})
    assert out["cuda_usable"] is False
    assert out["nvidia_smi"]["available"] is False
    assert "nvidia-smi" in (out["nvidia_smi"].get("reason") or "")


def test_torch_absent_is_not_reported_as_torch_broken(monkeypatch):
    """"no deep-learning stack" and "torch present but CUDA unavailable" need different
    fixes, so the probe must not collapse them into one negative."""
    import importlib.util

    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *a, **k: None if name == "torch" else real_find_spec(name, *a, **k))
    out = _handle_device_probe({})
    assert out["torch"]["installed"] is False
    assert "not installed" in (out["torch"].get("reason") or "")


def test_windows_wheel_layout_is_detected(tmp_path):
    """The Windows CUDA wheel has no nvidia/ namespace package at all: the runtime DLLs
    ship straight into torch/lib. Globbing only for POSIX .so files therefore reports a
    fully working Windows CUDA build as CPU-only, which is what made a cu132 RTX 5090
    install come back as 'CUDA is not usable in this build'."""
    lib = tmp_path / "torch" / "lib"
    lib.mkdir(parents=True)
    (lib / "cudart64_13.dll").write_bytes(b"")
    (lib / "cublas64_13.dll").write_bytes(b"")
    found = _find_cuda_runtime_libraries([tmp_path])
    assert any("cudart64_13.dll" in p for p in found), found
    # cublas carries neither 'cudart' nor an nvidia/ parent, so it also exercises the
    # post-glob filter that used to discard it.
    assert any("cublas64_13.dll" in p for p in found), found


def test_linux_wheel_layout_is_still_detected(tmp_path):
    """The POSIX layout the original patterns were written for must keep working."""
    lib = tmp_path / "nvidia" / "cuda_runtime" / "lib"
    lib.mkdir(parents=True)
    (lib / "libcudart.so.12").write_bytes(b"")
    found = _find_cuda_runtime_libraries([tmp_path])
    assert any("libcudart.so.12" in p for p in found), found


def test_unrelated_libraries_are_not_reported(tmp_path):
    """The filter exists to keep the headline meaningful; noise must not satisfy it."""
    lib = tmp_path / "torch" / "lib"
    lib.mkdir(parents=True)
    (lib / "torch_cpu.dll").write_bytes(b"")
    assert _find_cuda_runtime_libraries([tmp_path]) == []


def test_missing_roots_are_skipped(tmp_path):
    """Nonexistent roots are normal (a PyInstaller bundle has no site-packages)."""
    assert _find_cuda_runtime_libraries([tmp_path / "nope", tmp_path]) == []


def _fake_torch(version: str, cuda_version):
    """A stand-in torch module. __spec__ must be set because the probe calls
    importlib.util.find_spec("torch"), which rejects a bare module object."""
    import importlib.machinery
    import types

    mod = types.ModuleType("torch")
    mod.__spec__ = importlib.machinery.ModuleSpec("torch", loader=None)
    mod.__version__ = version
    mod.version = types.SimpleNamespace(cuda=cuda_version)
    available = cuda_version is not None
    mod.cuda = types.SimpleNamespace(
        is_available=lambda: available,
        device_count=lambda: 1 if available else 0,
        get_device_name=lambda i=0: "NVIDIA GeForce RTX 5090" if available else "",
        get_device_capability=lambda i=0: (12, 0) if available else (0, 0),
    )
    return mod


def test_cuda_build_is_recognised_from_torch_even_without_a_filesystem_hit(monkeypatch, tmp_path):
    """torch.version.cuda is the authoritative, platform-independent signal that the
    installed wheel is a CUDA build: None for CPU wheels, '13.2' for CUDA ones. It must
    be able to carry the headline on its own, so a PyInstaller bundle that repackages
    torch/lib somewhere unanticipated is not misreported as CPU-only."""
    import importlib.util
    import site
    import subprocess
    import sys

    # site/subprocess are imported inside the probe, so the stdlib modules themselves are
    # what has to be patched.
    # Hermetic: point the filesystem scan at an empty tree so the assertion is about the
    # torch fallback, not about whatever CUDA wheels the host happens to have installed.
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    monkeypatch.setattr(site, "getsitepackages", lambda: [])
    monkeypatch.setattr(shutil, "which", lambda _name: "nvidia-smi")
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0] if a else [], 0, "NVIDIA GeForce RTX 5090, 616.92\n", ""),
    )

    monkeypatch.setitem(sys.modules, "torch", _fake_torch("2.14.1+cu132", "13.2"))
    importlib.util.find_spec  # keep the real spec: the fake module is what must be found

    out = _handle_device_probe({})
    assert out["cuda_runtime_in_bundle"]["present"] is True
    assert out["cuda_runtime_in_bundle"]["source"] == "torch"
    assert out["cuda_usable"] is True


def test_cpu_only_torch_is_not_reported_as_a_cuda_build(monkeypatch, tmp_path):
    """The torch fallback must key off torch.version.cuda being set, not merely off torch
    being importable -- otherwise every CPU build would claim to bundle a CUDA runtime."""
    import site
    import sys

    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    monkeypatch.setattr(site, "getsitepackages", lambda: [])

    monkeypatch.setitem(sys.modules, "torch", _fake_torch("2.14.1+cpu", None))

    out = _handle_device_probe({})
    assert out["cuda_runtime_in_bundle"]["present"] is False
    assert out["cuda_runtime_in_bundle"]["source"] == "filesystem"
    assert out["cuda_usable"] is False

