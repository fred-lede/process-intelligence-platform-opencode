"""OptQuest-style parameter search (LHS + lightweight Monte Carlo evaluation).

三種 objective：maximize_yield / minimize_dpmo / hit_target(+Cpk 約束)。
演算法介面預留未來擴充（遺傳演算法等），不改 handler。
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .monte_carlo import predict_output
from .prediction import get_input_ranges
from .spc import compute_capability


def _lhs_samples(bounds, n, seed):
    """Latin Hypercube：每維 n 分層各一樣本，層內 uniform，層序隨機。"""
    rng = np.random.default_rng(seed)
    out = {}
    for col, (lo, hi) in bounds.items():
        strata = (np.arange(n) + rng.uniform(0.0, 1.0, n)) / n
        rng.shuffle(strata)
        out[col] = lo + strata * (hi - lo)
    return out


def _evaluate_points(fit, df, points, lsl, usl, n_eval_samples, seed):
    """每候選點：該點為 mu、歷史 sigma 為波動跑輕量蒙地卡羅 -> 指標。"""
    rng = np.random.default_rng(seed)
    input_cols = list(points[0].keys()) if points else []
    sigmas = {c: (float(df[c].std(ddof=1)) if len(df) > 1 and df[c].std(ddof=1) > 0 else 1.0)
              for c in input_cols}
    feature_names = fit.selected_inputs or fit.inputs
    categorical_levels = getattr(fit.model, "levels", {}) if fit.model_type == "doe_categorical_factorial" else {}
    results = []
    for pt in points:
        samples = {
            c: np.full(n_eval_samples, pt[c]) if c in categorical_levels
            else rng.normal(pt[c], sigmas[c], n_eval_samples)
            for c in input_cols
        }
        outputs = np.array([
            predict_output(fit.model_type, fit.coefficients or {},
                           {c: samples[c][i] for c in input_cols},
                           model=fit.model, feature_names=feature_names)
            for i in range(n_eval_samples)
        ], dtype=float)
        if lsl is not None or usl is not None:
            below = outputs < (lsl if lsl is not None else -np.inf)
            above = outputs > (usl if usl is not None else np.inf)
            ng = float(np.sum(below | above))
            yield_ = 1.0 - ng / n_eval_samples
            dpmo = (ng / n_eval_samples) * 1e6
            cap = compute_capability(outputs.tolist(), lsl=lsl, usl=usl, subgroup_size=1)
            cpk = cap.get("cpk")
        else:
            yield_, dpmo, cpk = None, None, None
        results.append({"point": pt, "yield": yield_, "dpmo": dpmo,
                        "predicted_mean": float(np.mean(outputs)), "cpk": cpk})
    return results


def _score(metric, objective, target_value):
    """越小越好（yield 以負分納入同一方向）。"""
    if objective == "maximize_yield":
        return -(metric["yield"] if metric["yield"] is not None else 0.0)
    if objective == "minimize_dpmo":
        return metric["dpmo"] if metric["dpmo"] is not None else 1e18
    return abs(metric["predicted_mean"] - (target_value if target_value is not None else 0.0))


def _feasible(metric, objective, cpk_min):
    if objective == "hit_target":
        return True if metric["cpk"] is None else metric["cpk"] >= cpk_min
    return True


def run_optquest(fit, df, objective, lsl, usl, target_value=None, cpk_min=1.33,
                 bounds=None, n_candidates=200, n_eval_samples=500, seed=42):
    if objective not in ("maximize_yield", "minimize_dpmo", "hit_target"):
        raise ValueError("objective must be maximize_yield, minimize_dpmo, or hit_target")
    if objective in ("maximize_yield", "minimize_dpmo") and lsl is None and usl is None:
        raise ValueError("LSL/USL required for yield/DPMO objectives")

    if bounds is None:
        ranges = get_input_ranges(df, fit.inputs)
        bounds = {c: (ranges[c]["min"], ranges[c]["max"]) for c in fit.inputs}
    for c, (lo, hi) in bounds.items():
        if lo > hi:
            raise ValueError(f"bounds for {c!r} inverted (min>max)")

    if fit.model_type == "doe_categorical_factorial" and getattr(fit.model, "levels", None):
        rng = np.random.default_rng(seed)
        levels = fit.model.levels
        points = [{c: levels[c][int(rng.integers(0, len(levels[c])))] for c in fit.inputs}
                  for _ in range(n_candidates)]
    else:
        points_raw = _lhs_samples(bounds, n_candidates, seed)
        points = [{c: (float(bounds[c][0]) if bounds[c][1] == bounds[c][0] else float(points_raw[c][i]))
                   for c in fit.inputs}
                  for i in range(n_candidates)]

    metrics = _evaluate_points(fit, df, points, lsl, usl, n_eval_samples, seed)

    trajectory = []
    best_idx = None
    best_score = None
    for i, m in enumerate(metrics):
        s = _score(m, objective, target_value)
        ok = _feasible(m, objective, cpk_min)
        if ok and (best_score is None or s < best_score):
            best_score, best_idx = s, i
        # best_so_far 統一為「負分數」→ 單調遞增（越大越好），供前端軌跡圖
        # 直接繪製收斂曲線：yield=+yield、dpmo=−dpmo、hit_target=−距離。
        shown = -best_score if best_score is not None else None
        trajectory.append({"step": i, "best_so_far": shown,
                           "point": dict(points[i]), "feasible": ok})

    if best_idx is None:
        best_idx = int(np.argmin([_score(m, objective, target_value) for m in metrics]))
        feasible = False
    else:
        # hit_target：target 不可達（最佳距離仍遠）→ feasible=false
        feasible = True
        if objective == "hit_target":
            best_dist = abs(metrics[best_idx]["predicted_mean"]
                            - (target_value if target_value is not None else 0.0))
            y_range = float(df[fit.target].max() - df[fit.target].min()) if len(df) > 0 else 0.0
            scale = y_range if y_range > 0 else 1.0
            if best_dist > 0.1 * scale:
                feasible = False

    m = metrics[best_idx]
    return {
        "objective": objective,
        "constraints": {"cpk_min": cpk_min},
        "best_point": dict(points[best_idx]),
        "best": {"yield": m["yield"], "dpmo": m["dpmo"],
                 "predicted_mean": m["predicted_mean"], "cpk": m["cpk"]},
        "feasible": feasible,
        "baseline": None,
        "trajectory": trajectory,
        "top_candidates": [
            {"point": metrics[i]["point"], "yield": metrics[i]["yield"],
             "dpmo": metrics[i]["dpmo"], "predicted_mean": metrics[i]["predicted_mean"],
             "cpk": metrics[i]["cpk"]}
            for i in sorted(range(len(metrics)),
                            key=lambda i: _score(metrics[i], objective, target_value))[:10]
        ],
        "n_candidates": n_candidates, "n_eval_samples": n_eval_samples, "seed": seed,
        "note": "搜尋結果為模型內插預測，套用前須實驗驗證。",
    }
