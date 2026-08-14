"""
Convergence metrics for multi-objective runs.

Hypervolume and Inverted Generational Distance are the two standard measures:
hypervolume says how much of the objective space a front dominates (coverage and
proximity in one number), IGD says how far the true front is from the one we
found (accuracy). Together they catch the two ways a multi-objective search
fails — converging to part of the front, or spreading across a worse one.

Everything here assumes minimisation.
"""

from __future__ import annotations

from typing import Iterable, Sequence, Tuple

import numpy as np

__all__ = [
    "non_dominated",
    "hypervolume",
    "inverted_generational_distance",
    "generational_distance",
]


def _as_matrix(points: Iterable[Sequence[float]]) -> np.ndarray:
    matrix = np.asarray(list(points), dtype=float)
    if matrix.size == 0:
        return np.empty((0, 0))
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    return matrix


def non_dominated(points: Iterable[Sequence[float]]) -> np.ndarray:
    """
    Return the non-dominated subset of `points` (Pareto-optimal, minimisation).

    A point is dominated when another point is at least as good in every
    objective and strictly better in at least one.
    """
    matrix = _as_matrix(points)
    if matrix.shape[0] == 0:
        return matrix

    keep = np.ones(matrix.shape[0], dtype=bool)
    for i in range(matrix.shape[0]):
        if not keep[i]:
            continue
        others = matrix[keep]
        weakly_better = np.all(others <= matrix[i], axis=1)
        strictly_better = np.any(others < matrix[i], axis=1)
        if np.any(weakly_better & strictly_better):
            keep[i] = False
    return matrix[keep]


def _hypervolume_2d(front: np.ndarray, reference: np.ndarray) -> float:
    """Exact hypervolume for two objectives by sweeping the sorted front."""
    ordered = front[np.argsort(front[:, 0])]
    volume = 0.0
    previous_f2 = reference[1]
    for f1, f2 in ordered:
        if f2 >= previous_f2:
            continue  # dominated in the sweep; contributes nothing
        volume += (reference[0] - f1) * (previous_f2 - f2)
        previous_f2 = f2
    return volume


def _hypervolume_monte_carlo(
    front: np.ndarray,
    reference: np.ndarray,
    n_samples: int,
    seed: int,
) -> float:
    """
    Monte-Carlo hypervolume estimate for three or more objectives.

    Exact hypervolume is exponential in the number of objectives. A seeded
    estimate keeps the harness reproducible and is accurate enough to show a
    convergence trend; it is not accurate enough to publish a small margin
    between two algorithms, which is why the method used is reported alongside
    the value.
    """
    lower = front.min(axis=0)
    box_lower = np.minimum(lower, reference)
    box_volume = float(np.prod(reference - box_lower))
    if box_volume <= 0.0:
        return 0.0

    rng = np.random.default_rng(seed)
    samples = rng.uniform(box_lower, reference, size=(n_samples, front.shape[1]))

    # A sample counts when at least one front point dominates it.
    dominated = np.zeros(n_samples, dtype=bool)
    for point in front:
        dominated |= np.all(samples >= point, axis=1)

    return box_volume * float(dominated.mean())


def hypervolume(
    points: Iterable[Sequence[float]],
    reference_point: Sequence[float],
    n_samples: int = 200_000,
    seed: int = 0,
) -> Tuple[float, str]:
    """
    Hypervolume dominated by `points` relative to `reference_point`.

    Returns the volume and the method used ("exact_2d", "monte_carlo" or
    "empty"), so a caller can tell an exact figure from an estimate.
    """
    reference = np.asarray(reference_point, dtype=float)
    matrix = _as_matrix(points)
    if matrix.shape[0] == 0:
        return 0.0, "empty"

    # Only points that the reference point dominates contribute volume.
    inside = matrix[np.all(matrix < reference, axis=1)]
    if inside.shape[0] == 0:
        return 0.0, "empty"

    front = non_dominated(inside)

    if front.shape[1] == 2:
        return _hypervolume_2d(front, reference), "exact_2d"
    return (
        _hypervolume_monte_carlo(front, reference, n_samples=n_samples, seed=seed),
        "monte_carlo",
    )


def _min_distances(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    """For each row of `source`, the Euclidean distance to the nearest row of `target`."""
    differences = source[:, None, :] - target[None, :, :]
    return np.sqrt(np.sum(differences**2, axis=2)).min(axis=1)


def inverted_generational_distance(
    points: Iterable[Sequence[float]],
    reference_front: Iterable[Sequence[float]],
) -> float:
    """
    Mean distance from each true-front point to the nearest found point.

    Lower is better. Because it measures from the *true* front outward, it
    punishes gaps in coverage as well as distance — a tight cluster sitting
    exactly on one end of the front still scores badly.
    """
    found = _as_matrix(points)
    truth = _as_matrix(reference_front)
    if found.shape[0] == 0 or truth.shape[0] == 0:
        return float("inf")
    return float(_min_distances(truth, found).mean())


def generational_distance(
    points: Iterable[Sequence[float]],
    reference_front: Iterable[Sequence[float]],
) -> float:
    """
    Mean distance from each found point to the nearest true-front point.

    Lower is better. Measures accuracy only, and is blind to coverage.
    """
    found = _as_matrix(points)
    truth = _as_matrix(reference_front)
    if found.shape[0] == 0 or truth.shape[0] == 0:
        return float("inf")
    return float(_min_distances(found, truth).mean())
