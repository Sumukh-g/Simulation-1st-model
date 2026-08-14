"""
One interface over every search strategy.

The point of this module is that callers — the benchmark harness now, the run
orchestrator later — never name a concrete optimiser. They ask for a backend by
name and drive it through `propose` / `observe`. That is what lets a stronger
implementation be added later without touching anything upstream of it.

Three backends ship as the defaults, and they are the existing, tested v1 code
rather than new implementations:

    evolutionary  NSGA-II style population search — good coverage, sample-hungry
    bayesian      GP surrogate with Chebyshev scalarisation — sample-efficient
    hybrid        both cooperating over one evaluation pool (the v1 engine)

A BoTorch backend is the intended fourth, specifically for multi-objective
Bayesian optimisation, where hypervolume-based acquisition (qEHVI/qNEHVI) does
something a scalarising GP fundamentally cannot. It is deliberately not here
yet: the benchmark harness exists to produce the evidence for whether it earns
its place before the dependency is taken on.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Protocol, Sequence, Tuple, runtime_checkable

import numpy as np

from .bandit import FidelityLevel
from .bayesian import BayesianOptimizer
from .evolutionary import EvolutionaryOptimizer
from .optimizer import Objective, OptimizerConfig, OptimizerStrategy, UnifiedOptimizer
from .stopping import StoppingConfig

__all__ = [
    "OptimiserBackend",
    "Evaluation",
    "create_backend",
    "list_backends",
    "register_backend",
]

# A single evaluated point: the parameters that were tried, and the objective
# values that came back from deterministic code.
Evaluation = Tuple[Dict[str, float], Dict[str, float]]


@runtime_checkable
class OptimiserBackend(Protocol):
    """
    The contract every search strategy satisfies.

    `propose` and `observe` are separate calls, and observe takes a batch, so a
    backend can be driven by a parallel evaluator that returns results out of
    order without the interface having to change.
    """

    name: str

    def propose(self, n: int) -> List[Dict[str, float]]:
        """Suggest `n` parameter dicts to evaluate next."""
        ...

    def observe(self, evaluations: Sequence[Evaluation]) -> None:
        """Feed evaluated points back into the strategy."""
        ...

    def state(self) -> Dict[str, Any]:
        """Serialisable snapshot, for the run ledger."""
        ...


BackendFactory = Callable[..., OptimiserBackend]
_BACKENDS: Dict[str, BackendFactory] = {}


def register_backend(name: str) -> Callable[[BackendFactory], BackendFactory]:
    """Register a backend factory under `name`."""

    def decorator(factory: BackendFactory) -> BackendFactory:
        _BACKENDS[name] = factory
        return factory

    return decorator


def list_backends() -> List[str]:
    """Names of every registered backend."""
    return sorted(_BACKENDS)


def create_backend(
    name: str,
    *,
    bounds: Dict[str, Tuple[float, float]],
    objective_names: Sequence[str],
    minimise: Sequence[bool] | None = None,
    seed: int | None = None,
    **options: Any,
) -> OptimiserBackend:
    """
    Build a backend by name.

    Args:
        bounds: Search box, keyed by parameter name.
        objective_names: Objectives in a fixed order.
        minimise: Per-objective direction; defaults to minimising all of them.
        seed: Seed for reproducibility.
        options: Backend-specific settings (population size, batch size, ...).
    """
    if name not in _BACKENDS:
        raise KeyError(
            f"unknown optimiser backend {name!r}; available: {', '.join(list_backends())}"
        )

    directions = list(minimise) if minimise is not None else [True] * len(objective_names)
    if len(directions) != len(objective_names):
        raise ValueError("minimise must have one entry per objective")

    return _BACKENDS[name](
        bounds=dict(bounds),
        objective_names=list(objective_names),
        minimise=directions,
        seed=seed,
        **options,
    )


def _sign_vector(minimise: Sequence[bool]) -> np.ndarray:
    """+1 where an objective is minimised, -1 where it is maximised."""
    return np.array([1.0 if m else -1.0 for m in minimise])


@register_backend("evolutionary")
class EvolutionaryBackend:
    """NSGA-II style population search over the full objective vector."""

    def __init__(
        self,
        bounds: Dict[str, Tuple[float, float]],
        objective_names: List[str],
        minimise: List[bool],
        seed: int | None = None,
        population_size: int = 50,
        mutation_rate: float = 0.1,
        crossover_rate: float = 0.9,
        **_: Any,
    ) -> None:
        self.name = "evolutionary"
        self._objective_names = objective_names
        self._optimiser = EvolutionaryOptimizer(
            bounds=bounds,
            objectives=objective_names,
            maximize=[not m for m in minimise],
            population_size=population_size,
            mutation_rate=mutation_rate,
            crossover_rate=crossover_rate,
            random_state=seed,
        )
        self._initialised = False

    def propose(self, n: int) -> List[Dict[str, float]]:
        if not self._initialised:
            self._initialised = True
            return self._optimiser.initialize_population()[:n]

        proposals = self._optimiser.evolve()
        # evolve() returns a generation; top it up if a smaller batch is asked for
        # than the population produces, and repeat-evolve if a larger one is.
        while len(proposals) < n:
            proposals.extend(self._optimiser.evolve())
        return proposals[:n]

    def observe(self, evaluations: Sequence[Evaluation]) -> None:
        for params, objectives in evaluations:
            self._optimiser.observe(params, objectives)

    def state(self) -> Dict[str, Any]:
        return {
            "backend": self.name,
            "generation": getattr(self._optimiser, "generation", 0),
        }


@register_backend("bayesian")
class BayesianBackend:
    """
    GP surrogate search, scalarised when there is more than one objective.

    With several objectives it follows ParEGO: draw fresh Chebyshev weights each
    iteration, re-scalarise the whole archive under those weights, refit, and
    propose. Refitting from the archive each time is what makes changing the
    weights legitimate — the surrogate is always consistent with the scalarisation
    it was trained on. It is sample-efficient but reaches the front one weighting
    at a time, which is exactly the limitation the hybrid is meant to cover.
    """

    def __init__(
        self,
        bounds: Dict[str, Tuple[float, float]],
        objective_names: List[str],
        minimise: List[bool],
        seed: int | None = None,
        n_restarts: int = 5,
        rho: float = 0.05,
        **_: Any,
    ) -> None:
        self.name = "bayesian"
        self._bounds = bounds
        self._objective_names = objective_names
        self._signs = _sign_vector(minimise)
        self._n_restarts = n_restarts
        self._rho = rho
        self._seed = seed
        self._rng = np.random.default_rng(seed)
        self._archive: List[Tuple[Dict[str, float], np.ndarray]] = []
        self._single_objective = len(objective_names) == 1
        self._iteration = 0
        self._optimiser = self._new_optimiser()

    def _new_optimiser(self) -> BayesianOptimizer:
        # The seed advances with the iteration. BayesianOptimizer re-seeds its
        # own RNG from random_state on every propose() call, so holding one seed
        # would make every iteration start its acquisition search from the same
        # points. Deriving the seed keeps runs reproducible without freezing the
        # search.
        derived_seed = None if self._seed is None else self._seed + self._iteration
        return BayesianOptimizer(
            bounds=self._bounds,
            maximize=False,  # always minimise the scalarised value
            n_restarts=self._n_restarts,
            random_state=derived_seed,
        )

    def _objective_matrix(self) -> np.ndarray:
        return np.array([values for _, values in self._archive])

    def _scalarise(self, matrix: np.ndarray, weights: np.ndarray) -> np.ndarray:
        """Augmented Chebyshev scalarisation (lower is better)."""
        # Normalise per objective so weights mean the same thing on every axis.
        lower = matrix.min(axis=0)
        spread = matrix.max(axis=0) - lower
        spread[spread <= 0.0] = 1.0
        normalised = (matrix - lower) / spread

        weighted = normalised * weights
        return weighted.max(axis=1) + self._rho * weighted.sum(axis=1)

    def propose(self, n: int) -> List[Dict[str, float]]:
        self._iteration += 1

        if not self._archive:
            # Nothing observed yet: fall back to the surrogate's own cold start.
            return self._optimiser.propose(n)

        # propose() fits the GP itself, so no explicit fit() call here.
        if self._single_objective:
            return self._optimiser.propose(n)

        weights = self._rng.dirichlet(np.ones(len(self._objective_names)))
        matrix = self._objective_matrix() * self._signs
        scores = self._scalarise(matrix, weights)

        self._optimiser = self._new_optimiser()
        for (params, _), score in zip(self._archive, scores):
            self._optimiser.observe(params, float(score))

        return self._optimiser.propose(n)

    def observe(self, evaluations: Sequence[Evaluation]) -> None:
        for params, objectives in evaluations:
            vector = np.array(
                [objectives[name] for name in self._objective_names], dtype=float
            )
            self._archive.append((params, vector))
            if self._single_objective:
                self._optimiser.observe(params, float(vector[0] * self._signs[0]))

    def state(self) -> Dict[str, Any]:
        return {
            "backend": self.name,
            "observations": len(self._archive),
            "scalarisation": "none" if self._single_objective else "augmented_chebyshev",
        }


@register_backend("hybrid")
class HybridBackend:
    """
    The v1 engine: Bayesian and evolutionary search sharing one evaluation pool.

    Delegates to `UnifiedOptimizer`, which splits each batch between the two
    strategies so acquisition-driven candidates and population-driven candidates
    compete on the same archive.
    """

    def __init__(
        self,
        bounds: Dict[str, Tuple[float, float]],
        objective_names: List[str],
        minimise: List[bool],
        seed: int | None = None,
        batch_size: int = 20,
        population_size: int = 50,
        bayesian_n_restarts: int | None = None,
        **_: Any,
    ) -> None:
        self.name = "hybrid"
        self._objective_names = objective_names

        config = OptimizerConfig(
            bounds=bounds,
            objectives=[
                Objective(name=name, maximize=not is_min)
                for name, is_min in zip(objective_names, minimise)
            ],
            strategy=OptimizerStrategy.HYBRID,
            population_size=population_size,
            batch_size=batch_size,
            random_state=seed,
            # Benchmark problems have a single fidelity, so fidelity selection
            # must not distort the evaluation budget: make every level cost the
            # same and leave the budget effectively unbounded.
            fidelity_costs={level: 1.0 for level in FidelityLevel},
            budget=float(10**9),
        )

        if bayesian_n_restarts is not None:
            # How hard the acquisition function is optimised. This dominates
            # wall-clock cost in high dimensions, so a caller trading search
            # quality for run time needs to be able to turn it down.
            config.bayesian_n_restarts = bayesian_n_restarts

        self._optimiser = UnifiedOptimizer(
            config=config,
            # The harness governs termination by evaluation budget; stopping
            # rules would end runs at different points and make the comparison
            # between backends meaningless.
            stopping_config=StoppingConfig(
                max_iterations=10**9,
                max_evaluations=10**9,
                min_iterations=10**9,
            ),
        )
        self._last_stop_reason = "none"

    def propose(self, n: int) -> List[Dict[str, float]]:
        return [candidate.params for candidate in self._optimiser.propose_batch(n)]

    def observe(self, evaluations: Sequence[Evaluation]) -> None:
        results = [
            {"params": params, "outcome": {"metrics": dict(objectives)}, "fidelity": "cheap"}
            for params, objectives in evaluations
        ]
        _, reason = self._optimiser.update(results)
        self._last_stop_reason = reason.value

    def state(self) -> Dict[str, Any]:
        snapshot = self._optimiser.get_state()
        snapshot["backend"] = self.name
        snapshot["stop_reason"] = self._last_stop_reason
        return snapshot
