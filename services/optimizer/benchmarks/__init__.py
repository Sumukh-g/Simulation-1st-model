"""
Optimiser validation on standard multi-objective benchmarks.

Domain-independent proof that the search engine works: analytic ZDT and DTLZ
problems with known Pareto fronts, measured by hypervolume and inverted
generational distance.
"""

from .harness import (
    BenchmarkConfig,
    BenchmarkResult,
    IterationRecord,
    compare_backends,
    run_benchmark,
)
from .metrics import (
    generational_distance,
    hypervolume,
    inverted_generational_distance,
    non_dominated,
)
from .problems import PROBLEM_NAMES, BenchmarkProblem, get_problem, list_problems

__all__ = [
    "BenchmarkConfig",
    "BenchmarkResult",
    "IterationRecord",
    "run_benchmark",
    "compare_backends",
    "BenchmarkProblem",
    "PROBLEM_NAMES",
    "get_problem",
    "list_problems",
    "hypervolume",
    "inverted_generational_distance",
    "generational_distance",
    "non_dominated",
]
