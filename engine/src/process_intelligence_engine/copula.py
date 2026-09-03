"""Copula-based joint anomaly probability (spec 14.4).

Supports three modes for combining anomaly occurrence events:

1. **Independent** — P(A∩B) = P(A)·P(B) (default when no correlation given).
2. **Correlation matrix** — Gaussian Copula with user-specified Pearson
   correlation matrix; transforms uniform marginals via the Cholesky
   factor of the correlation matrix, then applies the Gaussian CDF /
   inverse-CDF to recover joint probabilities.
3. **Direct joint probability** — user provides P(A∩B) explicitly for
   a pair of anomalies.

All outputs are plain Python types for clean JSON IPC serialization.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats


@dataclass
class CopulaResult:
    """Joint occurrence results for a set of anomalies."""

    mode: str  # "independent" | "gaussian_copula" | "direct"
    joint_probabilities: dict[str, float]
    pair_correlations: list[dict] | None = None
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "mode": self.mode,
            "joint_probabilities": self.joint_probabilities,
        }
        if self.pair_correlations:
            d["pair_correlations"] = self.pair_correlations
        if self.warning:
            d["warning"] = self.warning
        return d


def compute_joint_probabilities(
    anomalies: list[dict[str, Any]],
    correlation_matrix: list[list[float]] | None = None,
    direct_joints: dict[str, float] | None = None,
    seed: int | None = None,
    n_samples: int = 100_000,
) -> CopulaResult:
    """Compute joint occurrence probabilities for a set of anomalies.

    Args:
        anomalies: List of anomaly dicts, each with at least
            ``anomaly_id`` and ``occurrence_probability``.
        correlation_matrix: Optional Pearson correlation matrix
            (n×n) for Gaussian Copula mode. Must match ``len(anomalies)``.
        direct_joints: Optional dict mapping ``"id1&id2"`` → joint prob,
            overriding the correlation matrix for specific pairs.
        seed: Random seed for reproducibility.
        n_samples: Number of Monte Carlo samples for the Copula.

    Returns:
        CopulaResult with joint probabilities and metadata.
    """
    n = len(anomalies)
    if n == 0:
        return CopulaResult(mode="independent", joint_probabilities={})

    ids = [a.get("anomaly_id", f"anomaly_{i}") for i, a in enumerate(anomalies)]
    probs = np.array([max(0.0, min(1.0, a.get("occurrence_probability", 0.0))) for a in anomalies])

    # Sanity check
    if n > 1 and not all(0.0 <= p <= 1.0 for p in probs):
        return CopulaResult(
            mode="independent",
            joint_probabilities={},
            warning="Some occurrence probabilities are outside [0, 1]; clamped.",
        )

    # Single anomaly: joint = marginal
    if n == 1:
        return CopulaResult(
            mode="independent",
            joint_probabilities={ids[0]: float(probs[0])},
        )

    # ----- Direct joint probability mode -----
    if direct_joints and len(direct_joints) > 0:
        joint_probs: dict[str, float] = {}
        for combo_key, combo_prob in direct_joints.items():
            joint_probs[combo_key] = float(max(0.0, min(1.0, combo_prob)))
        return CopulaResult(
            mode="direct",
            joint_probabilities=joint_probs,
        )

    # ----- Gaussian Copula mode -----
    if correlation_matrix is not None and len(correlation_matrix) == n:
        try:
            R = np.array(correlation_matrix, dtype=float)
            _validate_correlation_matrix(R, n)
            samples = _gaussian_copula_samples(R, probs, n_samples, seed)
            return _compute_from_samples(ids, probs, samples, "gaussian_copula")
        except (np.linalg.LinAlgError, ValueError) as exc:
            # Fall back to independent with a warning
            return CopulaResult(
                mode="independent",
                joint_probabilities={
                    ids[i]: float(probs[i]) for i in range(n)
                },
                warning=f"Gaussian Copula failed ({exc}); falling back to independent assumption.",
            )

    # ----- Independent mode (default) -----
    return _independent_result(ids, probs)


def _validate_correlation_matrix(R: np.ndarray, n: int) -> None:
    """Validate that R is a proper correlation matrix."""
    if R.shape != (n, n):
        raise ValueError(f"Correlation matrix shape {R.shape} != ({n},{n})")
    diag = np.diag(R)
    if not np.allclose(diag, 1.0, atol=1e-6):
        raise ValueError("Diagonal of correlation matrix must be 1.0")
    eigvals = np.linalg.eigvalsh(R)
    if np.min(eigvals) < -1e-8:
        raise ValueError(f"Correlation matrix is not positive semidefinite (min eigenvalue: {eigvals.min():.6f})")


def _gaussian_copula_samples(
    R: np.ndarray,
    probs: np.ndarray,
    n_samples: int,
    seed: int | None,
) -> np.ndarray:
    """Generate uniform samples with joint structure from a Gaussian Copula.

    Returns shape (n_samples, n_anomalies) array of U[0,1] values.
    """
    rng = np.random.default_rng(seed)
    # Cholesky decomposition of correlation matrix
    L = np.linalg.cholesky(R)
    # Generate independent standard normal samples
    Z = rng.standard_normal((n_samples, len(probs)))
    # Apply Cholesky to induce correlation
    Z_corr = Z @ L.T
    # Transform to uniform via Gaussian CDF
    U = stats.norm.cdf(Z_corr)
    # Clip to (0, 1) to avoid exact 0/1 which would cause issues
    U = np.clip(U, 1e-10, 1 - 1e-10)
    return U


def _compute_from_samples(
    ids: list[str],
    probs: np.ndarray,
    U: np.ndarray,
    mode: str,
) -> CopulaResult:
    """Compute joint probabilities from Copula samples."""
    n = len(ids)
    joint_probs: dict[str, float] = {}

    # Marginal joint probabilities (each anomaly occurring)
    for i in range(n):
        # P(U_i <= p_i) ≈ p_i by construction, but compute from samples
        mask = U[:, i] <= probs[i]
        joint_probs[ids[i]] = float(mask.mean())

    # Pairwise joint probabilities
    pair_correlations: list[dict] = []
    for i in range(n):
        for j in range(i + 1, n):
            mask_i = U[:, i] <= probs[i]
            mask_j = U[:, j] <= probs[j]
            joint = float((mask_i & mask_j).mean())
            pair_correlations.append({
                "anomaly_a": ids[i],
                "anomaly_b": ids[j],
                "joint_probability": round(joint, 6),
                "independent_expected": round(float(probs[i] * probs[j]), 6),
                "correlation": round(joint / max(probs[i] * probs[j], 1e-10) - 1.0, 4)
                               if probs[i] > 0 and probs[j] > 0 else 0.0,
            })
            key = f"{ids[i]}&{ids[j]}"
            joint_probs[key] = joint

    return CopulaResult(mode=mode, joint_probabilities=joint_probs, pair_correlations=pair_correlations)


def _independent_result(ids: list[str], probs: np.ndarray) -> CopulaResult:
    """Compute joint probabilities assuming independence."""
    n = len(ids)
    joint_probs: dict[str, float] = {}

    # Marginals
    for i in range(n):
        joint_probs[ids[i]] = float(probs[i])

    # All pairwise joints
    pair_correlations: list[dict] = []
    for i in range(n):
        for j in range(i + 1, n):
            joint = float(probs[i] * probs[j])
            pair_correlations.append({
                "anomaly_a": ids[i],
                "anomaly_b": ids[j],
                "joint_probability": round(joint, 6),
                "independent_expected": round(joint, 6),
                "correlation": 0.0,
            })
            key = f"{ids[i]}&{ids[j]}"
            joint_probs[key] = joint

    # Triple-wise and higher (only if n >= 3)
    if n >= 3:
        from itertools import combinations
        for combo in combinations(range(n), 3):
            key = "&".join(ids[i] for i in combo)
            prob = float(np.prod(probs[list(combo)]))
            joint_probs[key] = prob

    return CopulaResult(mode="independent", joint_probabilities=joint_probs, pair_correlations=pair_correlations)
