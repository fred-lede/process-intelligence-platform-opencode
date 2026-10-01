"""Device probe: the engine-side answer to "can this build actually use CUDA?".

The probe exists because "cannot use CUDA" has several distinct causes -- no driver, a
CPU-only bundle, torch absent because the build ships no deep-learning stack -- and a
user who has just set the device to 'gpu' needs to know which one applies. It therefore
reports each piece separately plus one headline derived from them.
"""
import json
import shutil

from process_intelligence_engine.main import _handle_device_probe


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
