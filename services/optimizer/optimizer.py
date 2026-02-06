"""Unified optimizer with multi-objective, multi-fidelity support."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Tuple

import numpy as np

from .bandit import FidelityLevel, MultiFidelityBandit
from .bayesian import BayesianOptimizer
from .constraints import Constraint, ConstraintHandler, ConstraintReport
from .evolutionary import EvolutionaryOptimizer
from .stopping import StopReason, StoppingConfig, StoppingRules

logger = logging.getLogger(__name__)


class OptimizerStrategy(str, Enum):
    """Optimization strategy."""

    BAYESIAN = "bayesian"
    EVOLUTIONARY = "evolutionary"
    HYBRID = "hybrid"  # Use both, combine proposals


@dataclass
class Objective:
    """Definition of an optimization objective."""

    name: str
    maximize: bool = True
    weight: float = 1.0
    # Optional: extract from outcome
    extractor: Callable[[Dict[str, Any]], float] | None = None


@dataclass
class Candidate:
    """A candidate solution."""

    id: str
    params: Dict[str, float]
    fidelity: str = "cheap"
    objectives: Dict[str, float] | None = None
    constraint_report: ConstraintReport | None = None
    scenario_hash: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "params": self.params,
            "fidelity": self.fidelity,
            "objectives": self.objectives,
            "constraint_report": (
                self.constraint_report.to_dict() if self.constraint_report else None
            ),
            "scenario_hash": self.scenario_hash,
            "metadata": self.metadata,
        }


@dataclass
class ParetoPoint:
    """A point on the Pareto frontier."""

    candidate: Candidate
    rank: int = 0
    crowding_distance: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "rank": self.rank,
            "crowding_distance": self.crowding_distance,
        }


@dataclass
class OptimizerConfig:
    """Configuration for the unified optimizer."""

    # Parameter space
    bounds: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    # Objectives (for multi-objective)
    objectives: List[Objective] = field(default_factory=list)

    # Strategy
    strategy: OptimizerStrategy = OptimizerStrategy.HYBRID

    # Bayesian settings
    bayesian_n_restarts: int = 10

    # Evolutionary settings
    population_size: int = 50
    mutation_rate: float = 0.1
    crossover_rate: float = 0.9

    # Multi-fidelity
    fidelity_costs: Dict[str, float] | None = None
    budget: float = 1000.0

    # Batch size
    batch_size: int = 10

    # Random seed
    random_state: int | None = None


class UnifiedOptimizer:
    """
    Unified optimizer combining Bayesian, evolutionary, and bandit approaches.

    Features:
    - Multi-objective Pareto frontier tracking
    - Constraint handling (hard filters + soft penalties)
    - Multi-fidelity scheduling
    - Stopping rules
    - Explainable choices
    """

    def __init__(
        self,
        config: OptimizerConfig,
        constraints: List[Constraint] | None = None,
        stopping_config: StoppingConfig | None = None,
    ):
        self.config = config
        self.rng = np.random.RandomState(config.random_state)

        # Objectives
        if not config.objectives:
            # Default single objective
            config.objectives = [Objective(name="score", maximize=True)]

        self._objective_names = [o.name for o in config.objectives]
        self._maximize = [o.maximize for o in config.objectives]

        # Initialize components
        self._init_bayesian()
        self._init_evolutionary()
        self._init_bandit()

        # Constraint handler
        self.constraint_handler = ConstraintHandler(constraints or [])

        # Stopping rules
        self.stopping_rules = StoppingRules(stopping_config or StoppingConfig())

        # History
        self.candidates: List[Candidate] = []
        self.pareto_frontier: List[ParetoPoint] = []
        self.iteration = 0
        self._start_time = time.time()

        # Proposal tracking for explanations
        self._last_proposals: List[Candidate] = []
        self._proposal_sources: Dict[str, str] = {}  # candidate_id -> source

    def _init_bayesian(self) -> None:
        """Initialize Bayesian optimizer for primary objective."""
        if not self.config.bounds:
            self._bayesian = None
            return

        # Use first objective for single-objective Bayesian
        primary_obj = self.config.objectives[0]
        self._bayesian = BayesianOptimizer(
            bounds=self.config.bounds,
            maximize=primary_obj.maximize,
            n_restarts=self.config.bayesian_n_restarts,
            random_state=self.config.random_state,
        )

    def _init_evolutionary(self) -> None:
        """Initialize evolutionary optimizer for multi-objective."""
        if not self.config.bounds:
            self._evolutionary = None
            return

        self._evolutionary = EvolutionaryOptimizer(
            bounds=self.config.bounds,
            objectives=self._objective_names,
            maximize=self._maximize,
            population_size=self.config.population_size,
            mutation_rate=self.config.mutation_rate,
            crossover_rate=self.config.crossover_rate,
            random_state=self.config.random_state,
        )

    def _init_bandit(self) -> None:
        """Initialize multi-fidelity bandit."""
        self._bandit = MultiFidelityBandit(
            fidelity_costs=self.config.fidelity_costs,
            budget=self.config.budget,
            random_state=self.config.random_state,
        )

    def _generate_candidate_id(self, params: Dict[str, float]) -> str:
        """Generate unique ID for a candidate."""
        data = json.dumps(params, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:12]

    def _extract_objectives(
        self,
        outcome: Dict[str, Any],
    ) -> Dict[str, float]:
        """Extract objective values from outcome."""
        objectives = {}

        for obj in self.config.objectives:
            if obj.extractor:
                objectives[obj.name] = obj.extractor(outcome)
            else:
                # Try to find in metrics
                metrics = outcome.get("metrics", {})
                if isinstance(metrics, list):
                    for m in metrics:
                        if m.get("name") == obj.name:
                            objectives[obj.name] = m.get("value", 0.0)
                            break
                    else:
                        objectives[obj.name] = outcome.get(obj.name, 0.0)
                else:
                    objectives[obj.name] = metrics.get(obj.name, 0.0)

        return objectives

    def _select_fidelity(self, remaining: int) -> str:
        """Select fidelity level for next batch."""
        # Early iterations: use cheap
        if self.iteration < 3:
            return FidelityLevel.CHEAP.value

        fidelity = self._bandit.select_fidelity(remaining)
        return fidelity.value

    def propose_batch(self, batch_size: int | None = None) -> List[Candidate]:
        """
        Propose a batch of candidates to evaluate.

        Returns candidates with assigned fidelity levels.
        """
        batch_size = batch_size or self.config.batch_size
        proposals: List[Candidate] = []
        self._proposal_sources.clear()

        # Determine fidelity for this batch
        remaining_evals = (
            self.config.budget - self._bandit.remaining_budget
        ) / self._bandit.fidelity_costs.get(FidelityLevel.CHEAP, 1.0)
        fidelity = self._select_fidelity(int(remaining_evals))

        # Get proposals based on strategy
        if self.config.strategy == OptimizerStrategy.BAYESIAN:
            proposals = self._propose_bayesian(batch_size, fidelity)
        elif self.config.strategy == OptimizerStrategy.EVOLUTIONARY:
            proposals = self._propose_evolutionary(batch_size, fidelity)
        else:  # HYBRID
            # Split between strategies
            n_bayesian = batch_size // 2
            n_evolutionary = batch_size - n_bayesian

            bayesian_props = self._propose_bayesian(n_bayesian, fidelity)
            evo_props = self._propose_evolutionary(n_evolutionary, fidelity)
            proposals = bayesian_props + evo_props

        # Filter by hard constraints
        feasible = []
        for prop in proposals:
            report = self.constraint_handler.evaluate(prop.params)
            if report.all_satisfied:
                prop.constraint_report = report
                feasible.append(prop)
            else:
                # Try to generate replacement
                logger.debug(f"Candidate {prop.id} violates constraints, skipping")

        # If too few feasible, add random feasible candidates
        attempts = 0
        while len(feasible) < batch_size and attempts < batch_size * 3:
            params = self._random_params()
            report = self.constraint_handler.evaluate(params)
            if report.all_satisfied:
                cand = Candidate(
                    id=self._generate_candidate_id(params),
                    params=params,
                    fidelity=fidelity,
                    constraint_report=report,
                )
                feasible.append(cand)
                self._proposal_sources[cand.id] = "random_feasible"
            attempts += 1

        self._last_proposals = feasible[:batch_size]
        return self._last_proposals

    def _propose_bayesian(self, n: int, fidelity: str) -> List[Candidate]:
        """Get proposals from Bayesian optimizer."""
        if self._bayesian is None or n == 0:
            return []

        params_list = self._bayesian.propose(n)
        proposals = []

        for params in params_list:
            cand_id = self._generate_candidate_id(params)
            proposals.append(
                Candidate(
                    id=cand_id,
                    params=params,
                    fidelity=fidelity,
                )
            )
            self._proposal_sources[cand_id] = "bayesian"

        return proposals

    def _propose_evolutionary(self, n: int, fidelity: str) -> List[Candidate]:
        """Get proposals from evolutionary optimizer."""
        if self._evolutionary is None or n == 0:
            return []

        # Initialize population if needed
        if self.iteration == 0:
            self._evolutionary.initialize_population()

        # Evolve and get offspring
        params_list = self._evolutionary.evolve()[:n]
        proposals = []

        for params in params_list:
            cand_id = self._generate_candidate_id(params)
            proposals.append(
                Candidate(
                    id=cand_id,
                    params=params,
                    fidelity=fidelity,
                )
            )
            self._proposal_sources[cand_id] = "evolutionary"

        return proposals

    def _random_params(self) -> Dict[str, float]:
        """Generate random parameters within bounds."""
        return {
            name: self.rng.uniform(low, high)
            for name, (low, high) in self.config.bounds.items()
        }

    def update(
        self,
        results: List[Dict[str, Any]],
    ) -> Tuple[bool, StopReason]:
        """
        Update optimizer with simulation results.

        Args:
            results: List of dicts with 'params', 'outcome', and optionally 'fidelity'

        Returns:
            (should_stop, reason)
        """
        self.iteration += 1
        budget_spent = 0.0

        for result in results:
            params = result.get("params", {})
            outcome = result.get("outcome", {})
            fidelity = result.get("fidelity", "cheap")
            candidate_id = result.get("candidate_id") or self._generate_candidate_id(
                params
            )

            # Extract objectives
            objectives = self._extract_objectives(outcome)

            # Apply soft constraint penalties
            constraint_report = self.constraint_handler.evaluate(params, outcome)
            penalized_objectives = self.constraint_handler.apply_penalties(
                params, objectives, outcome
            )

            # Create/update candidate
            candidate = Candidate(
                id=candidate_id,
                params=params,
                fidelity=fidelity,
                objectives=penalized_objectives,
                constraint_report=constraint_report,
                metadata={"raw_objectives": objectives},
            )
            self.candidates.append(candidate)

            # Update Bayesian optimizer (primary objective)
            if self._bayesian and self._objective_names:
                primary_value = penalized_objectives.get(self._objective_names[0], 0.0)
                self._bayesian.observe(params, primary_value)

            # Update evolutionary optimizer
            if self._evolutionary:
                self._evolutionary.observe(params, penalized_objectives)

            # Update bandit
            fidelity_level = FidelityLevel(fidelity)
            primary_score = penalized_objectives.get(self._objective_names[0], 0.0)
            self._bandit.update(fidelity_level, primary_score)
            budget_spent += self._bandit.fidelity_costs.get(fidelity_level, 1.0)

        # Update Pareto frontier
        self._update_pareto_frontier()

        # Check stopping conditions
        best_score = None
        if self.candidates:
            primary_name = self._objective_names[0]
            scores = [
                c.objectives.get(primary_name, 0.0)
                for c in self.candidates
                if c.objectives
            ]
            if scores:
                maximize = self.config.objectives[0].maximize
                best_score = max(scores) if maximize else min(scores)

        self.stopping_rules.update(
            best_score=best_score,
            evaluations_this_step=len(results),
            budget_spent_this_step=budget_spent,
            wall_time_elapsed=time.time() - self._start_time,
        )

        return self.stopping_rules.check()

    def _update_pareto_frontier(self) -> None:
        """Update the Pareto frontier."""
        evaluated = [c for c in self.candidates if c.objectives]
        if not evaluated:
            return

        # Use evolutionary's Pareto computation
        if self._evolutionary:
            evo_frontier = self._evolutionary.get_pareto_frontier()
            self.pareto_frontier = []

            for params, objectives in evo_frontier:
                # Find matching candidate
                for c in evaluated:
                    if all(
                        abs(c.params.get(k, 0) - params.get(k, 0)) < 1e-10
                        for k in params
                    ):
                        self.pareto_frontier.append(ParetoPoint(candidate=c))
                        break

    def get_frontier(self) -> List[ParetoPoint]:
        """Get current Pareto frontier."""
        return self.pareto_frontier

    def get_best(self, objective: str | None = None) -> Candidate | None:
        """Get best candidate for an objective (or primary)."""
        objective = objective or self._objective_names[0]
        maximize = True
        for obj in self.config.objectives:
            if obj.name == objective:
                maximize = obj.maximize
                break

        evaluated = [c for c in self.candidates if c.objectives]
        if not evaluated:
            return None

        if maximize:
            return max(evaluated, key=lambda c: c.objectives.get(objective, 0.0))
        else:
            return min(evaluated, key=lambda c: c.objectives.get(objective, 0.0))

    def explain_choice(self, candidate_id: str) -> Dict[str, Any]:
        """Explain why a candidate was proposed."""
        source = self._proposal_sources.get(candidate_id, "unknown")

        explanation = {
            "candidate_id": candidate_id,
            "source": source,
            "iteration": self.iteration,
        }

        if source == "bayesian":
            explanation["reasoning"] = (
                "Proposed by Bayesian optimization using Expected Improvement "
                "acquisition function. This candidate is expected to improve "
                "upon the current best based on the GP surrogate model."
            )
            if self._bayesian and self._bayesian.best_params:
                explanation["current_best"] = self._bayesian.best_params
                explanation["best_score"] = self._bayesian.best_score

        elif source == "evolutionary":
            explanation["reasoning"] = (
                "Proposed by evolutionary optimization (NSGA-II). This candidate "
                "was generated through crossover and mutation of high-performing "
                "parents from the Pareto frontier."
            )
            explanation["generation"] = (
                self._evolutionary.generation if self._evolutionary else 0
            )

        elif source == "random_feasible":
            explanation["reasoning"] = (
                "Generated randomly to satisfy hard constraints when other "
                "methods produced infeasible candidates."
            )

        else:
            explanation["reasoning"] = "Origin unknown or candidate not found."

        # Add constraint info
        for c in self.candidates:
            if c.id == candidate_id and c.constraint_report:
                explanation["constraints"] = c.constraint_report.to_dict()
                break

        return explanation

    def explain_stopping(self) -> str:
        """Explain stopping condition."""
        return self.stopping_rules.explain()

    def get_state(self) -> Dict[str, Any]:
        """Get optimizer state for serialization."""
        return {
            "config": {
                "bounds": self.config.bounds,
                "objectives": [
                    {"name": o.name, "maximize": o.maximize, "weight": o.weight}
                    for o in self.config.objectives
                ],
                "strategy": self.config.strategy.value,
            },
            "iteration": self.iteration,
            "candidates_count": len(self.candidates),
            "pareto_size": len(self.pareto_frontier),
            "stopping_state": self.stopping_rules.state.to_dict(),
            "bandit_stats": self._bandit.get_statistics(),
        }

    def should_promote(self, candidate: Candidate) -> bool:
        """Check if a candidate should be promoted to higher fidelity."""
        if candidate.fidelity == FidelityLevel.HIGH.value:
            return False

        if not candidate.objectives:
            return False

        primary_score = candidate.objectives.get(self._objective_names[0], 0.0)
        fidelity_level = FidelityLevel(candidate.fidelity)

        return self._bandit.should_promote(fidelity_level, primary_score)

    def get_promotion_candidates(self, top_k: int = 5) -> List[Candidate]:
        """Get candidates that should be promoted to higher fidelity."""
        # Filter to cheap/mid fidelity evaluated candidates
        promotable = [
            c
            for c in self.candidates
            if c.objectives and c.fidelity != FidelityLevel.HIGH.value
        ]

        # Sort by primary objective
        primary = self._objective_names[0]
        maximize = self.config.objectives[0].maximize
        promotable.sort(
            key=lambda c: c.objectives.get(primary, 0.0),
            reverse=maximize,
        )

        # Return top k that should be promoted
        return [c for c in promotable[:top_k] if self.should_promote(c)]
