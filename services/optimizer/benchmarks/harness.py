"""
Benchmark harness: run a backend against an analytic problem and measure it.

This is the engine's own validation. It is domain-independent on purpose — if
the optimiser only looked good on a bundled domain pack, we would have proved
nothing about the platform. Every number here comes from evaluating analytic
functions, so a run is fully reproducible from its spec plus its seed.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Sequence

import numpy as np

from ..backends import create_backend
from .metrics import hypervolume, inverted_generational_distance, non_dominated
from .problems import BenchmarkProblem, get_problem

__all__ = [
    "BenchmarkConfig",
    "BenchmarkResult",
    "IterationRecord",
    "run_benchmark",
    "compare_backends",
]

# Points sampled from the analytic front when computing IGD.
REFERENCE_FRONT_POINTS = 200


@dataclass
class BenchmarkConfig:
    """One benchmark run: a problem, a backend, a budget and a seed."""

    problem: str
    backend: str = "hybrid"
    budget: int = 200
    batch_size: int = 20
    seed: int = 42
    # Resize the problem. None keeps the canonical size from the source paper.
    n_variables: int | None = None
    n_objectives: int | None = None
    backend_options: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.budget <= 0:
            raise ValueError("budget must be positive")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")


@dataclass
class IterationRecord:
    """Convergence state after one batch of evaluations."""

    iteration: int
    evaluations: int
    hypervolume: float
    igd: float
    front_size: int


@dataclass
class BenchmarkResult:
    """Everything a run produced, ready to serialise into the ledger."""

    problem: str
    backend: str
    seed: int
    budget: int
    batch_size: int
    n_evaluations: int
    n_objectives: int
    n_variables: int
    reference_point: List[float]
    hypervolume: float
    hypervolume_method: str
    igd: float
    front: List[List[float]]
    history: List[IterationRecord]
    wall_time_seconds: float
    backend_state: Dict[str, Any]

    @property
    def initial_hypervolume(self) -> float:
        return self.history[0].hypervolume if self.history else 0.0

    @property
    def initial_igd(self) -> float:
        return self.history[0].igd if self.history else float("inf")

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["history"] = [asdict(record) for record in self.history]
        return payload

    def summary(self) -> str:
        # Kept ASCII-only: this is printed by the CLI, and Windows consoles
        # default to a codepage that cannot encode typographic characters.
        return (
            f"{self.problem} | {self.backend} | seed {self.seed} | "
            f"{self.n_evaluations} evals -> "
            f"HV {self.hypervolume:.4f} ({self.hypervolume_method}), "
            f"IGD {self.igd:.4f}, front {len(self.front)} points, "
            f"{self.wall_time_seconds:.1f}s"
        )


def _evaluate_batch(
    problem: BenchmarkProblem,
    proposals: Sequence[Dict[str, float]],
) -> List[Dict[str, float]]:
    """Evaluate proposals with the problem's deterministic code."""
    return [problem.evaluate(problem.clip(params)) for params in proposals]


def run_benchmark(config: BenchmarkConfig) -> BenchmarkResult:
    """
    Run one backend against one problem for a fixed evaluation budget.

    Termination is by evaluation count, never by the backend's own stopping
    rules: comparing two strategies is only meaningful at equal budgets.
    """
    problem = get_problem(
        config.problem,
        n_variables=config.n_variables,
        n_objectives=config.n_objectives,
    )
    objective_names = problem.objective_names
    reference_front = problem.pareto_front(REFERENCE_FRONT_POINTS)

    backend = create_backend(
        config.backend,
        bounds=problem.bounds,
        objective_names=objective_names,
        minimise=[True] * problem.n_objectives,
        seed=config.seed,
        batch_size=config.batch_size,
        **config.backend_options,
    )

    archive: List[List[float]] = []
    history: List[IterationRecord] = []
    started = time.perf_counter()
    iteration = 0

    while len(archive) < config.budget:
        remaining = config.budget - len(archive)
        batch_size = min(config.batch_size, remaining)

        proposals = backend.propose(batch_size)[:batch_size]
        if not proposals:
            break

        objective_dicts = _evaluate_batch(problem, proposals)
        backend.observe(list(zip(proposals, objective_dicts)))

        archive.extend(
            [values[name] for name in objective_names] for values in objective_dicts
        )

        current_front = non_dominated(archive)
        volume, _ = hypervolume(current_front, problem.reference_point, seed=config.seed)
        iteration += 1
        history.append(
            IterationRecord(
                iteration=iteration,
                evaluations=len(archive),
                hypervolume=volume,
                igd=inverted_generational_distance(current_front, reference_front),
                front_size=int(current_front.shape[0]),
            )
        )

    final_front = non_dominated(archive)
    final_volume, method = hypervolume(
        final_front, problem.reference_point, seed=config.seed
    )

    return BenchmarkResult(
        problem=problem.name,
        backend=config.backend,
        seed=config.seed,
        budget=config.budget,
        batch_size=config.batch_size,
        n_evaluations=len(archive),
        n_objectives=problem.n_objectives,
        n_variables=problem.n_variables,
        reference_point=list(problem.reference_point),
        hypervolume=final_volume,
        hypervolume_method=method,
        igd=inverted_generational_distance(final_front, reference_front),
        front=np.asarray(final_front).tolist(),
        history=history,
        wall_time_seconds=time.perf_counter() - started,
        backend_state=backend.state(),
    )


def compare_backends(
    problem: str,
    backends: Sequence[str] = ("hybrid", "evolutionary", "bayesian"),
    budget: int = 200,
    batch_size: int = 20,
    seed: int = 42,
) -> Dict[str, BenchmarkResult]:
    """
    Run several backends on the same problem, budget and seed.

    This is the baseline comparison: whether cooperating search beats either
    strategy alone at an equal number of expensive evaluations.
    """
    return {
        name: run_benchmark(
            BenchmarkConfig(
                problem=problem,
                backend=name,
                budget=budget,
                batch_size=batch_size,
                seed=seed,
            )
        )
        for name in backends
    }
