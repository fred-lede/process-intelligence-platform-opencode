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
    # get() returns an isolated snapshot rather than the stored record, so a
    # caller cannot reach registry state through it. (This used to assert
    # `is fit` -- the very aliasing that let callers set .status directly.)
    got = reg.get(fit.model_id)
    assert got is not fit
    assert got.model_id == fit.model_id
    assert got.status == "draft"

    got.status = "approved"
    assert got.coefficients is not None
    got.coefficients["x"] = 999.0
    fresh = reg.get(fit.model_id)
    assert fresh.status == "draft"
    assert fresh.coefficients is not None
    assert fresh.coefficients["x"] != 999.0


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


def test_transition_unknown_status_raises():
    reg = ModelRegistry()
    fit = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    reg.register(fit)
    with pytest.raises(ValueError, match="Unknown status"):
        reg.transition(fit.model_id, "bogus")


def test_retire_from_approved():
    reg = ModelRegistry()
    fit = fit_doe_linear(_fit_df(), target="y", inputs=["x"])
    reg.register(fit)
    for s in ("pending_validation", "validated", "approved"):
        reg.transition(fit.model_id, s)
    reg.transition(fit.model_id, "retired")
    assert fit.status == "retired"


def test_delete_refuses_a_model_carrying_approval_weight():
    reg = ModelRegistry()
    mid = reg.register(fit_doe_linear(_fit_df(), target="y", inputs=["x"]))
    reg.transition(mid, "pending_validation")
    with pytest.raises(InvalidStatusTransition, match="Cannot delete"):
        reg.delete(mid)
    assert mid in reg.list_ids()


def test_delete_allows_draft_and_retired_models():
    reg = ModelRegistry()
    draft = reg.register(fit_doe_linear(_fit_df(), target="y", inputs=["x"]))
    retired = reg.register(fit_doe_linear(_fit_df(), target="y", inputs=["x"]))
    reg.transition(retired, "retired")
    reg.delete(draft)
    reg.delete(retired)
    assert reg.list_ids() == []


def test_snapshot_shares_the_estimator_but_isolates_the_metadata():
    # Sharing the estimator keeps reads cheap; everything governance-relevant
    # must be a copy.
    reg = ModelRegistry()
    mid = reg.register(fit_doe_linear(_fit_df(), target="y", inputs=["x"]))
    first, second = reg.get(mid), reg.get(mid)
    assert first.model is second.model
    assert first.inputs is not second.inputs
    assert first.metrics is not second.metrics


def test_transition_persists_even_if_the_returned_snapshot_is_mutated():
    reg = ModelRegistry()
    mid = reg.register(fit_doe_linear(_fit_df(), target="y", inputs=["x"]))
    returned = reg.transition(mid, "pending_validation")
    returned.status = "draft"
    assert reg.get(mid).status == "pending_validation"


def test_restore_status_is_the_only_way_around_the_transition_graph():
    reg = ModelRegistry()
    mid = reg.register(fit_doe_linear(_fit_df(), target="y", inputs=["x"]))
    # Not reachable by a single legal step from draft...
    with pytest.raises(InvalidStatusTransition):
        reg.transition(mid, "approved")
    # ...but the project loader restores a status that was already persisted.
    assert reg.restore_status(mid, "approved").status == "approved"
    assert reg.get(mid).status == "approved"
    with pytest.raises(ValueError, match="Unknown status"):
        reg.restore_status(mid, "bogus")
