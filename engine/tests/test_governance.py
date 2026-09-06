import pytest
import pandas as pd
import numpy as np
from process_intelligence_engine.modeling.governance import (
    check_model_applicability,
    check_doeb_ai_discrepancy,
    recommend_models,
)


def test_small_sample_warns_tree_models():
    df = pd.DataFrame({"x": np.random.rand(20), "y": np.random.rand(20)})
    warnings = check_model_applicability(df, target="y", inputs=["x"])
    assert any("tree" in w.lower() or "sample" in w.lower() for w in warnings)


def test_class_imbalance_warns():
    df = pd.DataFrame({"x": np.random.rand(100), "y": ["OK"] * 95 + ["NG"] * 5})
    warnings = check_model_applicability(df, target="y", inputs=["x"], is_binary=True)
    assert any("imbalance" in w.lower() for w in warnings)


def test_constant_column_warns():
    df = pd.DataFrame({"x": [1.0] * 50, "y": np.random.rand(50)})
    warnings = check_model_applicability(df, target="y", inputs=["x"])
    assert any("constant" in w.lower() for w in warnings)


def test_doeb_ai_discrepancy_small_diff():
    result = check_doeb_ai_discrepancy(
        doe_r2=0.85, ai_r2=0.88,
        ai_pred=[1.0, 2.0, 3.0],
        doe_pred=[1.05, 2.02, 2.98],
        scale=1.0,
    )
    assert result["needs_review"] == False


def test_doeb_ai_discrepancy_large_diff():
    result = check_doeb_ai_discrepancy(
        doe_r2=0.50, ai_r2=0.90,
        ai_pred=[1.0, 2.0, 3.0],
        doe_pred=[1.5, 2.8, 4.0],
        scale=1.0,
    )
    assert result["needs_review"] == True


def test_recommend_models_small_sample():
    recs = recommend_models(n_samples=30, n_features=3, is_binary_target=False, has_nonlinearity=False, need_interpretability=True)
    assert "doe_linear" in recs


def test_recommend_models_large_sample_no_interpretability():
    recs = recommend_models(n_samples=500, n_features=10, is_binary_target=False, has_nonlinearity=True, need_interpretability=False)
    assert "xgboost" in recs or "lightgbm" in recs


def test_recommend_models_binary():
    recs = recommend_models(n_samples=200, n_features=5, is_binary_target=True, has_nonlinearity=True, need_interpretability=True)
    assert "logistic_regression" in recs
    assert "xgboost" in recs


def test_verdict_supports():
    assert check_doeb_ai_discrepancy.__module__ == "process_intelligence_engine.modeling.governance"
    from process_intelligence_engine.modeling.governance import compute_experiment_verdict
    assert compute_experiment_verdict(5.0, 5.1, tolerance=0.5) == "supports"


def test_verdict_does_not_support():
    from process_intelligence_engine.modeling.governance import compute_experiment_verdict
    assert compute_experiment_verdict(5.0, 6.0, tolerance=0.5) == "does_not_support"


def test_verdict_needs_remodel():
    from process_intelligence_engine.modeling.governance import compute_experiment_verdict
    assert compute_experiment_verdict(5.0, 10.0, tolerance=0.5) == "needs_remodel"


def test_verdict_partially_supports():
    from process_intelligence_engine.modeling.governance import compute_experiment_verdict
    assert compute_experiment_verdict(5.0, 5.3, tolerance=0.5) == "partially_supports"


def test_recommend_next_experiment_returns_suggestions():
    import pandas as pd
    from process_intelligence_engine.modeling.governance import recommend_next_experiment
    from process_intelligence_engine.main import MODEL_REGISTRY
    import numpy as np

    # Create a simple model fit to register
    df = pd.DataFrame({"x": np.linspace(0, 10, 50), "y": np.linspace(0, 10, 50)})
    from process_intelligence_engine.modeling.fitters import fit_doe_linear
    fit = fit_doe_linear(df, target="y", inputs=["x"])
    MODEL_REGISTRY.register(fit)
    model_id = fit.model_id

    suggestions = recommend_next_experiment(model_id, df, n_suggestions=3)
    assert isinstance(suggestions, list)
    assert len(suggestions) > 0
    assert "condition" in suggestions[0]
    assert "rationale" in suggestions[0]


def test_verdict_derived_tolerance_from_spec_range():
    from process_intelligence_engine.modeling.governance import compute_experiment_verdict
    # spec_range=10 → tolerance=5; error=2 (ratio=0.4) → supports
    assert compute_experiment_verdict(5.0, 7.0, spec_range=10.0) == "supports"
    # error=4 (ratio=0.8) → partially_supports
    assert compute_experiment_verdict(5.0, 9.0, spec_range=10.0) == "partially_supports"
    # error=8 (ratio=1.6) → does_not_support
    assert compute_experiment_verdict(5.0, 13.0, spec_range=10.0) == "does_not_support"


def test_verdict_derived_tolerance_from_rmse():
    from process_intelligence_engine.modeling.governance import compute_experiment_verdict
    # rmse=1 → tolerance=2 (2×rmse); error=1 is within 0.5×2 → supports
    assert compute_experiment_verdict(5.0, 6.0, rmse=1.0) == "supports"


def test_verdict_classification_supports():
    from process_intelligence_engine.modeling.governance import compute_experiment_verdict
    assert compute_experiment_verdict(
        0, 0, is_classification=True, accuracy=0.92, recall=0.91
    ) == "supports"


def test_verdict_classification_does_not_support():
    from process_intelligence_engine.modeling.governance import compute_experiment_verdict
    assert compute_experiment_verdict(
        0, 0, is_classification=True, accuracy=0.70, recall=0.50
    ) == "does_not_support"


def test_verdict_classification_needs_remodel():
    from process_intelligence_engine.modeling.governance import compute_experiment_verdict
    assert compute_experiment_verdict(
        0, 0, is_classification=True, accuracy=0.55, recall=0.30
    ) == "needs_remodel"


def test_prediction_interval():
    from process_intelligence_engine.modeling.governance import compute_prediction_interval
    interval = compute_prediction_interval(predicted=5.0, rmse=0.5, n=100)
    assert interval["lower"] < 5.0 < interval["upper"]
    assert interval["confidence"] == 0.95
    assert interval["half_width"] > 0
