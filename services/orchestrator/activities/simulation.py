"""Simulation-related activities."""
import hashlib
import json
import random
import uuid
from typing import Any, Dict, List, Optional

from temporalio import activity
from sqlalchemy import select

from ..db import get_session
from services.api.db import models


@activity.defn
async def generate_scenarios(run_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generate scenarios for a run based on specification.
    
    For simple runs, this generates a grid or random sample.
    For optimization runs, the optimizer proposes scenarios.
    """
    run_id = run_spec["run_id"]
    budget = run_spec.get("budget", 100)
    seed_policy = run_spec.get("seed_policy", {})
    
    base_seed = seed_policy.get("base_seed", random.randint(0, 2**31))
    rng = random.Random(base_seed)
    
    # Get state and action templates
    initial_state = run_spec.get("initial_state", {})
    action_ranges = run_spec.get("action_ranges", {})
    
    scenarios = []
    for i in range(budget):
        # Generate actions (random sample from ranges)
        actions = {}
        for param, bounds in action_ranges.items():
            if isinstance(bounds, dict) and "min" in bounds and "max" in bounds:
                actions[param] = rng.uniform(bounds["min"], bounds["max"])
            elif isinstance(bounds, list):
                actions[param] = rng.choice(bounds)
            else:
                actions[param] = bounds  # Fixed value
        
        # Compute deterministic seed for this scenario
        scenario_seed = rng.randint(0, 2**31)
        
        # Compute scenario hash
        hash_data = {
            "run_id": run_id,
            "sequence": i,
            "state": initial_state,
            "actions": actions,
            "seed": scenario_seed,
        }
        scenario_hash = hashlib.sha256(
            json.dumps(hash_data, sort_keys=True).encode()
        ).hexdigest()
        
        scenarios.append({
            "scenario_id": str(uuid.uuid4()),
            "run_id": run_id,
            "sequence_number": i,
            "state": initial_state,
            "actions": actions,
            "fidelity": run_spec.get("default_fidelity", "mid"),
            "seed": scenario_seed,
            "scenario_hash": scenario_hash,
        })
    
    return scenarios


@activity.defn
async def execute_simulation_batch(
    domain_pack_id: str,
    domain_pack_version: str,
    scenarios: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Execute a batch of simulations.

    Uses in-process pack execution when RAY_ADDRESS is local (reliable on Windows
    demos). Falls back to the Ray Simulation Fabric for cluster addresses.
    """
    import os

    pack = await _resolve_pack(domain_pack_id, domain_pack_version, scenarios)
    address = (os.environ.get("RAY_ADDRESS") or "local").strip().lower()
    if address in ("", "local", "auto", "none"):
        return _run_batch_inprocess(
            domain_pack_id, domain_pack_version, scenarios, pack_instance=pack
        )

    if pack is None:
        return _run_batch_inprocess(domain_pack_id, domain_pack_version, scenarios)

    try:
        from services.sim_fabric.executor import get_fabric

        fabric = get_fabric()
        return await fabric.run_batch(
            domain_pack_name=domain_pack_id,
            domain_pack_version=domain_pack_version,
            scenarios=scenarios,
        )
    except Exception as exc:
        activity.logger.warning(
            "Ray fabric failed (%s); falling back to in-process simulation", exc
        )
        return _run_batch_inprocess(
            domain_pack_id, domain_pack_version, scenarios, pack_instance=pack
        )


async def _resolve_pack(
    domain_pack_id: str, domain_pack_version: str, scenarios: List[Dict[str, Any]]
):
    import compute.domain_packs  # noqa: F401
    from compute.domain_packs.sdk import DomainPackRegistry
    from compute.domain_packs.ephemeral_pack import load_ephemeral_pack_for_run

    pack = DomainPackRegistry.create_instance(domain_pack_id, domain_pack_version)
    if pack is not None:
        return pack
    if not scenarios:
        return None
    run_id = scenarios[0].get("run_id")
    if not run_id:
        return None
    return await load_ephemeral_pack_for_run(str(run_id), domain_pack_id)


def _run_batch_inprocess(
    domain_pack_name: str,
    domain_pack_version: str,
    scenarios: List[Dict[str, Any]],
    pack_instance: Any | None = None,
) -> List[Dict[str, Any]]:
    """Run scenarios against a domain pack in this process (no Ray)."""
    import compute.domain_packs  # noqa: F401
    from compute.domain_packs.sdk import DomainPackRegistry, Fidelity

    pack = pack_instance or DomainPackRegistry.create_instance(
        domain_pack_name, domain_pack_version
    )
    if pack is None:
        return [
            {
                "scenario_id": s.get("scenario_id"),
                "status": "failed",
                "error": f"Domain pack not found: {domain_pack_name}:{domain_pack_version}",
            }
            for s in scenarios
        ]

    results: List[Dict[str, Any]] = []
    for scenario in scenarios:
        scenario_id = scenario.get("scenario_id", "unknown")
        try:
            fidelity_raw = scenario.get("fidelity", "mid")
            try:
                fidelity = Fidelity(fidelity_raw)
            except Exception:
                fidelity = Fidelity.MID
            state = pack.validate_state(scenario.get("state", {}))
            actions = pack.validate_actions(scenario.get("actions", {}))
            outcome = pack.simulate(
                state=state,
                actions=actions,
                fidelity=fidelity,
                seed=int(scenario.get("seed", 0)),
                scenario_id=str(scenario_id),
                run_id=str(scenario.get("run_id", "unknown")),
            )
            scored = pack.score(outcome)
            full_outcome = (
                outcome.model_dump() if hasattr(outcome, "model_dump") else outcome.dict()
            )
            metric_values = []
            if hasattr(scored, "metrics"):
                for m in scored.metrics:
                    if hasattr(m, "model_dump"):
                        metric_values.append(m.model_dump())
                    elif isinstance(m, dict):
                        metric_values.append(m)
                    else:
                        metric_values.append(
                            {"name": getattr(m, "name", "metric"), "value": float(getattr(m, "value", 0))}
                        )
            # Keep the Temporal activity payload small. Heavy arrays such as
            # spatial grids/heatmaps live in raw_output/final_state and can blow
            # past Temporal's 4MB gRPC message limit; downstream only needs the
            # scored metrics (plus a couple of light scalars).
            slim_outcome: Dict[str, Any] = {"metrics": metric_values}
            if isinstance(full_outcome, dict):
                for light_key in ("runtime_seconds", "is_feasible"):
                    if full_outcome.get(light_key) is not None:
                        slim_outcome[light_key] = full_outcome[light_key]
            results.append(
                {
                    "scenario_id": scenario_id,
                    "status": "completed",
                    "outcome": slim_outcome,
                    "scenario_hash": scenario.get("scenario_hash"),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "scenario_id": scenario_id,
                    "status": "failed",
                    "error": str(exc),
                    "scenario_hash": scenario.get("scenario_hash"),
                }
            )
    return results


@activity.defn
async def score_outcomes(
    run_id: str,
    outcomes: List[Dict[str, Any]],
    rubric_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Score simulation outcomes.
    
    Uses the Judge service for deterministic scoring.
    """
    scored_results = []
    
    for outcome in outcomes:
        if outcome.get("status") != "completed":
            scored_results.append({
                "scenario_id": outcome.get("scenario_id"),
                "status": "failed",
                "error": outcome.get("error"),
            })
            continue
        
        # Extract metrics from outcome
        outcome_data = outcome.get("outcome", {})
        
        # Simple scoring (would call Judge service in production)
        score = None
        if "metrics" in outcome_data:
            # Average of all metric values
            metrics = outcome_data["metrics"]
            if isinstance(metrics, list):
                values = [m.get("value", 0) for m in metrics]
                score = sum(values) / len(values) if values else 0
        
        scored_results.append({
            "scenario_id": outcome.get("scenario_id"),
            "run_id": run_id,
            "status": "scored",
            "outcome": outcome_data,
            "score": score,
            "rubric_id": rubric_id,
        })
    
    return scored_results


@activity.defn
async def judge_score_outcomes(
    run_id: str,
    outcomes: List[Dict[str, Any]],
    rubric_version_id: Optional[str] = None,
    rubric_id: Optional[str] = None,
    benchmarks: Optional[List[Dict[str, Any]]] = None,
    objectives: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Deterministic scoring using rubric weights and benchmarks.

    When no rubric is configured, fall back to the formalized objectives so the
    score still reflects the user's intent: each objective metric contributes
    ``value * weight``, signed by its direction (``+`` for maximize, ``-`` for
    minimize). This keeps rankings meaningful without a stored rubric.
    """
    benchmarks = benchmarks or []
    rubric_weights: Dict[str, float] = {}
    async with get_session() as session:
        result = None
        if rubric_version_id:
            result = await session.execute(
                select(models.RubricWeight).where(
                    models.RubricWeight.rubric_version_id == uuid.UUID(rubric_version_id)
                )
            )
        elif rubric_id:
            version_rows = await session.execute(
                select(models.RubricVersion)
                .where(models.RubricVersion.rubric_id == uuid.UUID(rubric_id))
                .order_by(models.RubricVersion.version.desc())
                .limit(1)
            )
            version = version_rows.scalar_one_or_none()
            if version:
                result = await session.execute(
                    select(models.RubricWeight).where(
                        models.RubricWeight.rubric_version_id == version.id
                    )
                )

        if result is not None:
            for row in result.scalars().all():
                rubric_weights[row.metric_name] = row.weight

    # Direction sign per metric; defaults to +1 (higher is better).
    direction_sign: Dict[str, float] = {}
    if not rubric_weights and objectives:
        for metric in objectives.get("metrics", []) or []:
            name = metric.get("name")
            if not name:
                continue
            rubric_weights[name] = float(metric.get("weight", 1.0))
            direction_sign[name] = (
                -1.0 if metric.get("direction") == "minimize" else 1.0
            )

    scored_results = []
    for outcome in outcomes:
        if outcome.get("status") not in {"completed", "cached"}:
            scored_results.append(
                {
                    "scenario_id": outcome.get("scenario_id"),
                    "scenario_instance_id": outcome.get("scenario_instance_id"),
                    "status": "failed",
                    "error": outcome.get("error"),
                }
            )
            continue

        metrics_list = outcome.get("outcome", {}).get("metrics", []) or []
        metrics = {m.get("name"): m.get("value", 0.0) for m in metrics_list}

        # If no rubric/objective weights, score all returned metrics equally.
        if not rubric_weights and metrics:
            for name in metrics:
                rubric_weights[name] = 1.0
                direction_sign[name] = 1.0

        breakdown = []
        score = 0.0
        for metric_name, weight in rubric_weights.items():
            value = metrics.get(metric_name, 0.0)
            contribution = value * weight * direction_sign.get(metric_name, 1.0)
            score += contribution
            breakdown.append(
                {
                    "metric": metric_name,
                    "value": value,
                    "contribution": contribution,
                }
            )

        benchmark_results = []
        for benchmark in benchmarks:
            metric_name = benchmark.get("metric_name")
            threshold = benchmark.get("threshold_value")
            threshold_type = benchmark.get("threshold_type")
            value = metrics.get(metric_name)
            passed = None
            if value is not None and threshold is not None:
                if threshold_type == "min":
                    passed = value >= threshold
                elif threshold_type == "max":
                    passed = value <= threshold
            benchmark_results.append(
                {
                    "benchmark_id": benchmark.get("id"),
                    "metric_name": metric_name,
                    "threshold_type": threshold_type,
                    "threshold_value": threshold,
                    "value": value,
                    "passed": passed,
                }
            )

        scored_results.append(
            {
                "scenario_id": outcome.get("scenario_id"),
                "scenario_instance_id": outcome.get("scenario_instance_id"),
                "run_id": run_id,
                "status": "scored",
                "outcome": outcome.get("outcome", {}),
                "state": outcome.get("state"),
                "actions": outcome.get("actions"),
                "seed": outcome.get("seed"),
                "score": score,
                "breakdown": breakdown,
                "benchmark_results": benchmark_results,
            }
        )

    return scored_results


@activity.defn
async def aggregate_results(
    run_id: str,
    scored_results: List[Dict[str, Any]],
    objectives: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Aggregate scored results into a run summary.
    """
    completed = [r for r in scored_results if r.get("status") == "scored"]
    failed = [r for r in scored_results if r.get("status") == "failed"]
    
    scores = [r["score"] for r in completed if r.get("score") is not None]
    
    best_score = max(scores) if scores else None
    best_scenario = None
    if best_score is not None:
        for r in completed:
            if r.get("score") == best_score:
                best_scenario = r.get("scenario_id")
                break
    
    return {
        "run_id": run_id,
        "total_scenarios": len(scored_results),
        "completed": len(completed),
        "failed": len(failed),
        "best_score": best_score,
        "best_scenario_id": best_scenario,
        "mean_score": sum(scores) / len(scores) if scores else None,
        "score_std": None,  # Would compute standard deviation
    }


@activity.defn
async def seal_run(run_id: str) -> Dict[str, Any]:
    """
    Seal a run, making it immutable.
    """
    # Would update database to set is_sealed = True
    return {
        "run_id": run_id,
        "sealed": True,
    }
