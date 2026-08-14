"""
Standard multi-objective benchmark problems (ZDT and DTLZ suites).

These exist to validate the optimiser itself, independently of any domain.
They are analytic functions with known Pareto fronts, so convergence can be
measured rather than asserted — which is the only way to show the search engine
works without borrowing credibility from a domain pack.

All problems are minimisation problems and are evaluated by deterministic code:
the same decision vector always produces the same objective vector.

ZDT5 is deliberately absent. It is defined over binary strings, and every
optimiser backend here searches a continuous box; including it would mean
either a fake continuous relaxation or a special-cased encoding, neither of
which tells you anything true about the engine.

References:
    Zitzler, Deb & Thiele (2000), Evolutionary Computation 8(2), 173–195.
    Deb, Thiele, Laumanns & Zitzler (2002), Scalable test problems for
    evolutionary multi-objective optimization.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

import numpy as np

__all__ = [
    "BenchmarkProblem",
    "PROBLEM_NAMES",
    "get_problem",
    "list_problems",
]


@dataclass(frozen=True)
class BenchmarkProblem:
    """
    An analytic multi-objective minimisation problem.

    Attributes:
        name: Canonical problem name, e.g. "zdt1".
        n_variables: Dimensionality of the decision space.
        n_objectives: Number of objectives (all minimised).
        bounds: Per-variable (low, high) box, keyed by variable name.
        evaluate_vector: Maps a decision vector to an objective vector.
        reference_point: Dominated point used as the origin for hypervolume.
        pareto_front: Sampler for the analytic Pareto front, used by IGD.
    """

    name: str
    n_variables: int
    n_objectives: int
    bounds: Dict[str, Tuple[float, float]]
    evaluate_vector: Callable[[np.ndarray], np.ndarray]
    reference_point: Tuple[float, ...]
    pareto_front: Callable[[int], np.ndarray]
    description: str = ""
    variable_names: Tuple[str, ...] = field(default=())

    @property
    def objective_names(self) -> List[str]:
        return [f"f{i + 1}" for i in range(self.n_objectives)]

    def evaluate(self, params: Dict[str, float]) -> Dict[str, float]:
        """Evaluate a named parameter dict, returning named objectives."""
        vector = np.array([params[name] for name in self.variable_names], dtype=float)
        values = self.evaluate_vector(vector)
        return dict(zip(self.objective_names, (float(v) for v in values)))

    def clip(self, params: Dict[str, float]) -> Dict[str, float]:
        """Clamp a parameter dict into the problem's box."""
        clipped = {}
        for name, value in params.items():
            low, high = self.bounds[name]
            clipped[name] = min(max(float(value), low), high)
        return clipped


def _box(n_variables: int, low: float, high: float) -> Dict[str, Tuple[float, float]]:
    return {f"x{i + 1}": (low, high) for i in range(n_variables)}


def _names(n_variables: int) -> Tuple[str, ...]:
    return tuple(f"x{i + 1}" for i in range(n_variables))


# ─── ZDT suite (bi-objective) ────────────────────────────────────────────────
def _zdt1(x: np.ndarray) -> np.ndarray:
    n = x.size
    f1 = x[0]
    g = 1.0 + 9.0 * np.sum(x[1:]) / (n - 1)
    f2 = g * (1.0 - math.sqrt(f1 / g))
    return np.array([f1, f2])


def _zdt2(x: np.ndarray) -> np.ndarray:
    n = x.size
    f1 = x[0]
    g = 1.0 + 9.0 * np.sum(x[1:]) / (n - 1)
    f2 = g * (1.0 - (f1 / g) ** 2)
    return np.array([f1, f2])


def _zdt3(x: np.ndarray) -> np.ndarray:
    n = x.size
    f1 = x[0]
    g = 1.0 + 9.0 * np.sum(x[1:]) / (n - 1)
    ratio = f1 / g
    f2 = g * (1.0 - math.sqrt(ratio) - ratio * math.sin(10.0 * math.pi * f1))
    return np.array([f1, f2])


def _zdt4(x: np.ndarray) -> np.ndarray:
    n = x.size
    f1 = x[0]
    tail = x[1:]
    g = 1.0 + 10.0 * (n - 1) + np.sum(tail**2 - 10.0 * np.cos(4.0 * np.pi * tail))
    f2 = g * (1.0 - math.sqrt(f1 / g))
    return np.array([f1, f2])


def _zdt6(x: np.ndarray) -> np.ndarray:
    n = x.size
    f1 = 1.0 - math.exp(-4.0 * x[0]) * math.sin(6.0 * math.pi * x[0]) ** 6
    g = 1.0 + 9.0 * (np.sum(x[1:]) / (n - 1)) ** 0.25
    f2 = g * (1.0 - (f1 / g) ** 2)
    return np.array([f1, f2])


def _front_zdt1(n_points: int) -> np.ndarray:
    f1 = np.linspace(0.0, 1.0, n_points)
    return np.column_stack([f1, 1.0 - np.sqrt(f1)])


def _front_zdt2(n_points: int) -> np.ndarray:
    f1 = np.linspace(0.0, 1.0, n_points)
    return np.column_stack([f1, 1.0 - f1**2])


def _front_zdt3(n_points: int) -> np.ndarray:
    # ZDT3's front is disconnected; these are the five intervals of f1 on which
    # the analytic curve is non-dominated.
    intervals = [
        (0.0000000000, 0.0830015349),
        (0.1822287280, 0.2577623634),
        (0.4093136748, 0.4538821041),
        (0.6183967944, 0.6525117038),
        (0.8233317983, 0.8518328654),
    ]
    per_interval = max(1, n_points // len(intervals))
    samples = []
    for low, high in intervals:
        f1 = np.linspace(low, high, per_interval)
        f2 = 1.0 - np.sqrt(f1) - f1 * np.sin(10.0 * np.pi * f1)
        samples.append(np.column_stack([f1, f2]))
    return np.vstack(samples)


def _front_zdt6(n_points: int) -> np.ndarray:
    # f1 is bounded below by its value at x1 = 1 under the optimal tail.
    f1 = np.linspace(0.2807753191, 1.0, n_points)
    return np.column_stack([f1, 1.0 - f1**2])


# ─── DTLZ suite (scalable in objectives) ─────────────────────────────────────
def _dtlz_g_rastrigin(tail: np.ndarray) -> float:
    """DTLZ1/DTLZ3 distance function — heavily multimodal."""
    k = tail.size
    return 100.0 * (
        k + float(np.sum((tail - 0.5) ** 2 - np.cos(20.0 * np.pi * (tail - 0.5))))
    )


def _dtlz_g_sphere(tail: np.ndarray) -> float:
    """DTLZ2/DTLZ4 distance function."""
    return float(np.sum((tail - 0.5) ** 2))


def _dtlz1_objectives(x: np.ndarray, n_objectives: int) -> np.ndarray:
    g = _dtlz_g_rastrigin(x[n_objectives - 1:])
    values = np.empty(n_objectives)
    for i in range(n_objectives):
        product = 0.5 * (1.0 + g)
        for j in range(n_objectives - 1 - i):
            product *= x[j]
        if i > 0:
            product *= 1.0 - x[n_objectives - 1 - i]
        values[i] = product
    return values


def _dtlz2_style_objectives(
    x: np.ndarray,
    n_objectives: int,
    g: float,
) -> np.ndarray:
    values = np.empty(n_objectives)
    for i in range(n_objectives):
        product = 1.0 + g
        for j in range(n_objectives - 1 - i):
            product *= math.cos(0.5 * math.pi * x[j])
        if i > 0:
            product *= math.sin(0.5 * math.pi * x[n_objectives - 1 - i])
        values[i] = product
    return values


def _make_dtlz(number: int, n_objectives: int, k: int) -> Callable[[np.ndarray], np.ndarray]:
    if number == 1:
        def evaluate(x: np.ndarray) -> np.ndarray:
            return _dtlz1_objectives(x, n_objectives)
    elif number == 2:
        def evaluate(x: np.ndarray) -> np.ndarray:
            g = _dtlz_g_sphere(x[n_objectives - 1:])
            return _dtlz2_style_objectives(x, n_objectives, g)
    elif number == 3:
        def evaluate(x: np.ndarray) -> np.ndarray:
            g = _dtlz_g_rastrigin(x[n_objectives - 1:])
            return _dtlz2_style_objectives(x, n_objectives, g)
    elif number == 4:
        alpha = 100.0

        def evaluate(x: np.ndarray) -> np.ndarray:
            biased = x.copy()
            biased[: n_objectives - 1] = biased[: n_objectives - 1] ** alpha
            g = _dtlz_g_sphere(x[n_objectives - 1:])
            return _dtlz2_style_objectives(biased, n_objectives, g)
    else:
        raise ValueError(f"DTLZ{number} is not implemented")

    del k  # kept in the signature for symmetry with the problem definitions
    return evaluate


def _simplex_weights(n_points: int, n_objectives: int) -> np.ndarray:
    """
    Quasi-uniform points on the unit simplex, used to sample DTLZ fronts.

    Deterministic by construction so IGD is reproducible run to run.
    """
    if n_objectives == 2:
        f1 = np.linspace(0.0, 1.0, n_points)
        return np.column_stack([f1, 1.0 - f1])

    # Regular grid on the simplex, then trimmed to the requested count.
    divisions = 1
    while math.comb(divisions + n_objectives - 1, n_objectives - 1) < n_points:
        divisions += 1

    points: List[List[float]] = []

    def recurse(remaining: int, depth: int, current: List[float]) -> None:
        if depth == n_objectives - 1:
            points.append(current + [remaining / divisions])
            return
        for value in range(remaining + 1):
            recurse(remaining - value, depth + 1, current + [value / divisions])

    recurse(divisions, 0, [])
    return np.array(points)


def _front_dtlz1(n_objectives: int) -> Callable[[int], np.ndarray]:
    def sample(n_points: int) -> np.ndarray:
        # Front is the hyperplane sum(f) = 0.5.
        return 0.5 * _simplex_weights(n_points, n_objectives)

    return sample


def _front_dtlz_sphere(n_objectives: int) -> Callable[[int], np.ndarray]:
    def sample(n_points: int) -> np.ndarray:
        # Front is the unit sphere in the positive orthant.
        weights = _simplex_weights(n_points, n_objectives)
        norms = np.linalg.norm(weights, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return weights / norms

    return sample


# Each entry is (default n_variables, evaluator, front sampler, reference point,
# description). ZDT problems are all bi-objective by definition.
_ZDT_DEFINITIONS = {
    "zdt1": (30, _zdt1, _front_zdt1, (1.1, 1.1), "Convex front"),
    "zdt2": (30, _zdt2, _front_zdt2, (1.1, 1.1), "Non-convex front"),
    "zdt3": (30, _zdt3, _front_zdt3, (1.1, 2.1), "Disconnected front"),
    "zdt4": (10, _zdt4, _front_zdt1, (1.1, 1.1), "Multimodal, many local fronts"),
    "zdt6": (10, _zdt6, _front_zdt6, (1.1, 1.1), "Non-uniform front density"),
}

# (k, front sampler factory, description). n_variables defaults to
# n_objectives + k - 1, which is the convention in the original paper.
_DTLZ_DEFINITIONS = {
    "dtlz1": (5, _front_dtlz1, "Linear front, multimodal distance function"),
    "dtlz2": (10, _front_dtlz_sphere, "Spherical front"),
    "dtlz3": (10, _front_dtlz_sphere, "Spherical front, many local fronts"),
    "dtlz4": (10, _front_dtlz_sphere, "Spherical front, biased density"),
}


def _build_zdt(name: str, n_variables: int | None) -> BenchmarkProblem:
    default_vars, evaluate, front, reference, description = _ZDT_DEFINITIONS[name]
    n_vars = n_variables or default_vars
    if n_vars < 2:
        raise ValueError(f"{name} needs at least 2 variables, got {n_vars}")

    if name == "zdt4":
        # x1 stays in [0, 1]; the remaining variables live in [-5, 5].
        bounds = {"x1": (0.0, 1.0)}
        bounds.update({f"x{i + 1}": (-5.0, 5.0) for i in range(1, n_vars)})
    else:
        bounds = _box(n_vars, 0.0, 1.0)

    return BenchmarkProblem(
        name=name,
        n_variables=n_vars,
        n_objectives=2,
        bounds=bounds,
        evaluate_vector=evaluate,
        reference_point=reference,
        pareto_front=front,
        description=description,
        variable_names=_names(n_vars),
    )


def _build_dtlz(
    name: str,
    n_variables: int | None,
    n_objectives: int | None,
) -> BenchmarkProblem:
    k, front_factory, description = _DTLZ_DEFINITIONS[name]
    number = int(name[-1])
    n_objs = n_objectives or 3
    if n_objs < 2:
        raise ValueError(f"{name} needs at least 2 objectives, got {n_objs}")

    n_vars = n_variables or (n_objs + k - 1)
    if n_vars < n_objs:
        raise ValueError(
            f"{name} needs at least as many variables as objectives "
            f"({n_objs}), got {n_vars}"
        )

    # DTLZ1's front sits on the hyperplane sum(f) = 0.5, so 0.6 per axis
    # dominates it; the sphere-front problems need slightly more than 1.0.
    reference = (0.6,) * n_objs if number == 1 else (1.2,) * n_objs

    return BenchmarkProblem(
        name=name,
        n_variables=n_vars,
        n_objectives=n_objs,
        bounds=_box(n_vars, 0.0, 1.0),
        evaluate_vector=_make_dtlz(number, n_objs, k),
        reference_point=reference,
        pareto_front=front_factory(n_objs),
        description=f"{description} ({n_objs} objectives)",
        variable_names=_names(n_vars),
    )


PROBLEM_NAMES: Tuple[str, ...] = tuple(sorted({*_ZDT_DEFINITIONS, *_DTLZ_DEFINITIONS}))


def get_problem(
    name: str,
    n_variables: int | None = None,
    n_objectives: int | None = None,
) -> BenchmarkProblem:
    """
    Build a benchmark problem, optionally resized.

    Both suites are scalable, and the dimensionality and objective count are the
    two axes along which a hybrid search is expected to gain or lose against its
    baselines — so they are parameters, not constants. Omitting them gives the
    canonical sizes from the original papers.

    Raises:
        KeyError: if the problem name is unknown.
        ValueError: if the requested size is invalid for the problem.
    """
    key = name.lower()
    if key in _ZDT_DEFINITIONS:
        if n_objectives is not None and n_objectives != 2:
            raise ValueError(f"{key} is bi-objective by definition; got {n_objectives}")
        return _build_zdt(key, n_variables)
    if key in _DTLZ_DEFINITIONS:
        return _build_dtlz(key, n_variables, n_objectives)

    raise KeyError(
        f"unknown benchmark problem {name!r}; available: {', '.join(PROBLEM_NAMES)}"
    )


def list_problems() -> List[str]:
    """Names of every registered benchmark problem."""
    return list(PROBLEM_NAMES)
