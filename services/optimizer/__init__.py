"""GSIP Optimizer Service."""
from .bayesian import BayesianOptimizer
from .evolutionary import EvolutionaryOptimizer
from .bandit import MultiFidelityBandit, FidelityLevel
from .constraints import (
    Constraint,
    ConstraintHandler,
    ConstraintReport,
    ConstraintType,
    bounds_constraint,
    metric_threshold_constraint,
)
from .stopping import StopReason, StoppingConfig, StoppingRules
from .optimizer import (
    Candidate,
    Objective,
    OptimizerConfig,
    OptimizerStrategy,
    ParetoPoint,
    UnifiedOptimizer,
)
from .backends import (
    Evaluation,
    OptimiserBackend,
    create_backend,
    list_backends,
    register_backend,
)

__all__ = [
    # Core optimizers
    "BayesianOptimizer",
    "EvolutionaryOptimizer",
    "MultiFidelityBandit",
    "FidelityLevel",
    # Unified optimizer
    "UnifiedOptimizer",
    "OptimizerConfig",
    "OptimizerStrategy",
    "Objective",
    "Candidate",
    "ParetoPoint",
    # Constraints
    "Constraint",
    "ConstraintHandler",
    "ConstraintReport",
    "ConstraintType",
    "bounds_constraint",
    "metric_threshold_constraint",
    # Stopping
    "StopReason",
    "StoppingConfig",
    "StoppingRules",
    # Backend interface
    "OptimiserBackend",
    "Evaluation",
    "create_backend",
    "list_backends",
    "register_backend",
]
