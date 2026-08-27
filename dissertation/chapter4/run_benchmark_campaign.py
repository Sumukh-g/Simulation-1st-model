#!/usr/bin/env python3
"""
Equal-budget optimiser campaign for Chapter 4.

This script does not modify application source. It drives the existing
benchmark harness and an external random-search baseline that uses the same
problem evaluators, metrics, budget and seeds.
"""
from __future__ import annotations

import csv
import json
import sys
import time
import traceback
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
try:
    from sklearn.exceptions import ConvergenceWarning

    warnings.filterwarnings("ignore", category=ConvergenceWarning)
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.optimizer.benchmarks import (  # noqa: E402
    BenchmarkConfig,
    get_problem,
    hypervolume,
    inverted_generational_distance,
    non_dominated,
    run_benchmark,
)
from services.optimizer.benchmarks.harness import REFERENCE_FRONT_POINTS  # noqa: E402

OUT = Path(__file__).resolve().parent / "evidence"
FIG = Path(__file__).resolve().parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

COMMIT = "7803baa721a12ca19e26e700425fe7be94bfc3a4"
SEEDS = list(range(1, 11))
BUDGET = 200
BATCH = 20
ZDT_VARS = 5
BACKENDS = ("evolutionary", "bayesian", "hybrid", "random")
PROBLEMS = (
    {
        "problem": "zdt1",
        "n_variables": ZDT_VARS,
        "n_objectives": 2,
        "notes": "Principal two-objective baseline; 5 variables match the repository smoke spec rather than the 30-variable canonical size.",
    },
    {
        "problem": "zdt2",
        "n_variables": ZDT_VARS,
        "n_objectives": 2,
        "notes": "Non-convex front; same dimensionality and budget as ZDT1.",
    },
    {
        "problem": "dtlz2",
        "n_variables": None,
        "n_objectives": 3,
        "notes": "Three-objective spherical front; default n_variables = n_objectives + 10 - 1 = 12.",
    },
)


def _run_random(problem_name: str, n_variables, n_objectives, seed: int) -> Dict[str, Any]:
    """Uniform random search with the same evaluation budget as the GSIP backends."""
    problem = get_problem(problem_name, n_variables=n_variables, n_objectives=n_objectives)
    rng = np.random.default_rng(seed)
    names = list(problem.variable_names)
    lows = np.array([problem.bounds[n][0] for n in names], dtype=float)
    highs = np.array([problem.bounds[n][1] for n in names], dtype=float)
    reference_front = problem.pareto_front(REFERENCE_FRONT_POINTS)
    archive: List[List[float]] = []
    history = []
    started = time.perf_counter()
    remaining = BUDGET
    iteration = 0
    while remaining > 0:
        batch = min(BATCH, remaining)
        samples = rng.uniform(lows, highs, size=(batch, len(names)))
        for row in samples:
            params = {name: float(value) for name, value in zip(names, row)}
            outcome = problem.evaluate(problem.clip(params))
            archive.append([outcome[obj] for obj in problem.objective_names])
        remaining -= batch
        iteration += 1
        front = non_dominated(archive)
        volume, _ = hypervolume(front, problem.reference_point, seed=seed)
        history.append(
            {
                "iteration": iteration,
                "evaluations": len(archive),
                "hypervolume": volume,
                "igd": inverted_generational_distance(front, reference_front),
                "front_size": int(front.shape[0]),
            }
        )
    front = non_dominated(archive)
    volume, method = hypervolume(front, problem.reference_point, seed=seed)
    return {
        "problem": problem.name,
        "backend": "random",
        "seed": seed,
        "budget": BUDGET,
        "batch_size": BATCH,
        "n_evaluations": len(archive),
        "n_objectives": problem.n_objectives,
        "n_variables": problem.n_variables,
        "reference_point": list(problem.reference_point),
        "hypervolume": volume,
        "hypervolume_method": method,
        "igd": inverted_generational_distance(front, reference_front),
        "front": np.asarray(front).tolist(),
        "history": history,
        "wall_time_seconds": time.perf_counter() - started,
        "backend_state": {"backend": "random", "sampler": "uniform_box"},
        "status": "completed",
        "failure_reason": "",
    }


def _run_one(job: Dict[str, Any]) -> Dict[str, Any]:
    backend = job["backend"]
    problem = job["problem"]
    seed = job["seed"]
    n_variables = job["n_variables"]
    n_objectives = job["n_objectives"]
    try:
        if backend == "random":
            payload = _run_random(problem, n_variables, n_objectives, seed)
        else:
            result = run_benchmark(
                BenchmarkConfig(
                    problem=problem,
                    backend=backend,
                    budget=BUDGET,
                    batch_size=BATCH,
                    seed=seed,
                    n_variables=n_variables,
                    n_objectives=n_objectives,
                )
            )
            payload = result.to_dict()
            payload["status"] = "completed"
            payload["failure_reason"] = ""
        payload["run_id"] = f"{problem}-{backend}-seed{seed}"
        payload["commit"] = COMMIT
        payload["environment"] = "chapter4-cloud-agent-2026-08-27"
        payload["notes"] = job["notes"]
        payload["feasible_rate"] = None
        payload["variables"] = payload.get("n_variables")
        payload["objectives"] = payload.get("n_objectives")
        payload["population_size"] = 50 if backend in {"evolutionary", "hybrid"} else None
        payload["generations"] = None
        payload["initial_samples"] = None
        return payload
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": f"{problem}-{backend}-seed{seed}",
            "commit": COMMIT,
            "problem": problem,
            "backend": backend,
            "seed": seed,
            "variables": n_variables,
            "objectives": n_objectives,
            "budget": BUDGET,
            "batch_size": BATCH,
            "n_evaluations": 0,
            "hypervolume": None,
            "igd": None,
            "front": [],
            "history": [],
            "front_size": 0,
            "wall_time_seconds": None,
            "status": "failed",
            "failure_reason": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "environment": "chapter4-cloud-agent-2026-08-27",
            "notes": job["notes"],
        }


def _jobs() -> List[Dict[str, Any]]:
    jobs = []
    for spec in PROBLEMS:
        for backend in BACKENDS:
            for seed in SEEDS:
                jobs.append(
                    {
                        "problem": spec["problem"],
                        "backend": backend,
                        "seed": seed,
                        "n_variables": spec["n_variables"],
                        "n_objectives": spec["n_objectives"],
                        "notes": spec["notes"],
                    }
                )
    return jobs


def _replay_checks() -> Dict[str, Any]:
    """Same-seed exact replay and changed-seed divergence on evolutionary ZDT1."""
    cfg = BenchmarkConfig(
        problem="zdt1",
        backend="evolutionary",
        budget=60,
        batch_size=20,
        seed=123,
        n_variables=ZDT_VARS,
    )
    first = run_benchmark(cfg)
    second = run_benchmark(cfg)
    other = run_benchmark(
        BenchmarkConfig(
            problem="zdt1",
            backend="evolutionary",
            budget=60,
            batch_size=20,
            seed=124,
            n_variables=ZDT_VARS,
        )
    )
    return {
        "same_seed": {
            "seed": 123,
            "budget": 60,
            "hypervolume_match": first.hypervolume == second.hypervolume,
            "igd_match": first.igd == second.igd,
            "front_match": first.front == second.front,
            "history_match": [h.__dict__ for h in first.history]
            == [h.__dict__ for h in second.history],
            "first_hypervolume": first.hypervolume,
            "second_hypervolume": second.hypervolume,
            "first_igd": first.igd,
            "second_igd": second.igd,
            "comparison": "exact",
        },
        "changed_seed": {
            "seed_a": 123,
            "seed_b": 124,
            "fronts_differ": first.front != other.front,
            "hypervolume_a": first.hypervolume,
            "hypervolume_b": other.hypervolume,
            "igd_a": first.igd,
            "igd_b": other.igd,
        },
    }


def main() -> int:
    jobs = _jobs()
    results_path = OUT / "benchmark_runs.jsonl"
    print(
        f"{datetime.now(timezone.utc).isoformat()} starting {len(jobs)} runs "
        f"(budget={BUDGET}, seeds={SEEDS[0]}-{SEEDS[-1]})",
        flush=True,
    )
    results: List[Dict[str, Any]] = []
    # Two workers: Bayesian GP fits are memory and CPU heavy.
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_run_one, job): job for job in jobs}
        done = 0
        for future in as_completed(futures):
            payload = future.result()
            results.append(payload)
            done += 1
            with results_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload) + "\n")
            status = payload.get("status")
            print(
                f"[{done}/{len(jobs)}] {payload.get('run_id')} {status} "
                f"HV={payload.get('hypervolume')} IGD={payload.get('igd')} "
                f"t={payload.get('wall_time_seconds')}",
                flush=True,
            )

    replay = _replay_checks()
    bundle = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "commit": COMMIT,
        "budget": BUDGET,
        "batch_size": BATCH,
        "seeds": SEEDS,
        "backends": list(BACKENDS),
        "problems": list(PROBLEMS),
        "n_jobs": len(jobs),
        "results": results,
        "replay": replay,
    }
    (OUT / "benchmark_campaign.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    csv_path = OUT / "benchmark_runs.csv"
    fieldnames = [
        "run_id",
        "commit",
        "problem",
        "backend",
        "seed",
        "variables",
        "objectives",
        "budget",
        "batch_size",
        "population_size",
        "generations",
        "initial_samples",
        "hypervolume",
        "igd",
        "front_size",
        "feasible_rate",
        "wall_time_seconds",
        "status",
        "failure_reason",
        "environment",
        "notes",
        "hypervolume_method",
        "n_evaluations",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in results:
            out = dict(row)
            out["front_size"] = len(row.get("front") or [])
            out["variables"] = row.get("variables") or row.get("n_variables")
            out["objectives"] = row.get("objectives") or row.get("n_objectives")
            writer.writerow(out)

    print(f"wrote {OUT / 'benchmark_campaign.json'}")
    print(f"wrote {csv_path}")
    print(f"replay: {json.dumps(replay)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
