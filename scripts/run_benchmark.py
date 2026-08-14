#!/usr/bin/env python
"""
Run the optimiser against standard multi-objective benchmarks.

The engine's own validation, independent of any domain pack. A run is fully
determined by its spec plus its seed, so the same command reproduces the same
numbers.

Examples:
    # From a YAML spec (reproducible, version-controlled)
    python scripts/run_benchmark.py --spec configs/benchmarks/zdt1_smoke.yaml

    # Ad hoc
    python scripts/run_benchmark.py --problem zdt1 --backend hybrid --budget 200

    # Compare every backend on one problem at an equal budget
    python scripts/run_benchmark.py --problem zdt1 --compare --budget 200

    # Persist the full convergence history
    python scripts/run_benchmark.py --spec configs/benchmarks/zdt1_smoke.yaml \
        --output results/zdt1.json
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List

# The GP refits on every iteration and its hyperparameter search routinely hits
# a bound or gives up early. That is expected on a surrogate this small and says
# nothing about the run; left unfiltered it buries the results table.
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
try:
    from sklearn.exceptions import ConvergenceWarning

    warnings.filterwarnings("ignore", category=ConvergenceWarning)
except ImportError:
    pass

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.optimizer import list_backends  # noqa: E402
from services.optimizer.benchmarks import (  # noqa: E402
    BenchmarkConfig,
    BenchmarkResult,
    list_problems,
    run_benchmark,
)

DEFAULT_BACKENDS = ("hybrid", "evolutionary", "bayesian")


def _load_spec(path: Path) -> List[BenchmarkConfig]:
    """Read one or more run configurations from a YAML spec."""
    import yaml

    with path.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle) or {}

    if "runs" not in document:
        raise ValueError(f"{path} has no 'runs' key")

    defaults: Dict[str, Any] = document.get("defaults", {})
    configs: List[BenchmarkConfig] = []
    for entry in document["runs"]:
        merged = {**defaults, **entry}
        backends = merged.pop("backends", None)
        if backends:
            for backend in backends:
                configs.append(BenchmarkConfig(backend=backend, **merged))
        else:
            configs.append(BenchmarkConfig(**merged))
    return configs


def _configs_from_args(args: argparse.Namespace) -> List[BenchmarkConfig]:
    backends = DEFAULT_BACKENDS if args.compare else (args.backend,)
    return [
        BenchmarkConfig(
            problem=args.problem,
            backend=backend,
            budget=args.budget,
            batch_size=args.batch_size,
            seed=args.seed,
            n_variables=args.n_variables,
            n_objectives=args.n_objectives,
        )
        for backend in backends
    ]


def _print_table(results: List[BenchmarkResult]) -> None:
    header = (
        f"{'problem':<10} {'backend':<13} {'seed':>5} {'evals':>7} "
        f"{'HV':>10} {'IGD':>9} {'front':>6} {'secs':>7}"
    )
    print()
    print(header)
    print("-" * len(header))
    for result in results:
        print(
            f"{result.problem:<10} {result.backend:<13} {result.seed:>5} "
            f"{result.n_evaluations:>7} {result.hypervolume:>10.4f} "
            f"{result.igd:>9.4f} {len(result.front):>6} "
            f"{result.wall_time_seconds:>7.1f}"
        )
    print()


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the optimiser on ZDT/DTLZ benchmark problems.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--spec", type=Path, help="YAML spec describing one or more runs")
    parser.add_argument("--problem", default="zdt1", help=f"one of: {', '.join(list_problems())}")
    parser.add_argument("--backend", default="hybrid", help=f"one of: {', '.join(list_backends())}")
    parser.add_argument("--compare", action="store_true", help="run every backend on the problem")
    parser.add_argument("--budget", type=int, default=200, help="total evaluations per run")
    parser.add_argument("--batch-size", type=int, default=20, help="evaluations per iteration")
    parser.add_argument("--seed", type=int, default=42, help="seed for reproducibility")
    parser.add_argument("--n-variables", type=int, default=None, help="resize the decision space")
    parser.add_argument("--n-objectives", type=int, default=None, help="DTLZ objective count")
    parser.add_argument("--output", type=Path, default=None, help="write full results as JSON")
    parser.add_argument("--quiet", action="store_true", help="only print the summary table")
    args = parser.parse_args(argv)

    configs = _load_spec(args.spec) if args.spec else _configs_from_args(args)

    results: List[BenchmarkResult] = []
    for config in configs:
        if not args.quiet:
            print(
                f"running {config.problem} with {config.backend} "
                f"(budget {config.budget}, seed {config.seed}) ...",
                flush=True,
            )
        result = run_benchmark(config)
        results.append(result)
        if not args.quiet:
            print(f"  {result.summary()}", flush=True)

    _print_table(results)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        payload = {"results": [result.to_dict() for result in results]}
        with args.output.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        print(f"wrote {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
