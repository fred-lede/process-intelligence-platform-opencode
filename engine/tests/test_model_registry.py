"""Tests for immutable model version registry and status machine."""
import pandas as pd
import pytest

from process_intelligence_engine.modeling.fitters import fit_doe_linear
from process_intelligence_engine.modeling.registry import ModelRegistry, InvalidStatusTransition


def _fit_df():
    import numpy as np
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 1, 60)
    y = 2.0 + 3.0 * x + rng.normal(0, 0.01, 60)
    return pd.DataFrame({"x": x, "y": y})


def test_register_assigns_id_and_status_draft():
    reg = ModelRegistry()
    fit = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    reg.register(fit)
    assert fit.model_id
    assert fit.status == "draft"
    assert reg.get(fit.model_id) is fit


def test_register_increments_version():
    reg = ModelRegistry()
    fit1 = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    fit2 = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    reg.register(fit1)
    reg.register(fit2)
    assert fit1.version == 1
    assert fit2.version == 2


def test_list_models_returns_registered():
    reg = ModelRegistry()
    fit = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    reg.register(fit)
    ids = reg.list_ids()
    assert fit.model_id in ids


def test_unknown_status_transition_raises():
    reg = ModelRegistry()
    fit = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    reg.register(fit)
    with pytest.raises(InvalidStatusTransition):
        # cannot go draft -> approved without passing through validation
        reg.transition(fit.model_id, "approved")


def test_valid_transition_draft_to_pending():
    reg = ModelRegistry()
    fit = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    reg.register(fit)
    reg.transition(fit.model_id, "pending_validation")
    assert fit.status == "pending_validation"


def test_full_chain_to_approved():
    reg = ModelRegistry()
    fit = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    reg.register(fit)
    for s in ("pending_validation", "validated", "approved"):
        reg.transition(fit.model_id, s)
    assert fit.status == "approved"
