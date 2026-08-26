"""Ray-based simulation executor with full observability."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import ray

from .artifacts import ArtifactRecord, get_artifact_pipeline
from .cache import get_result_cache
from .config import settings
from .invariants import InvariantChecker
from .isolation import IsolationConfig, IsolationMode, get_isolation_strategy
from .tracing import (
    decrement_active_simulations,
    get_tracer,
    increment_active_simulations,
    record_artifact_size,
    record_cache_hit,
    record_cache_miss,
    record_invariant_violation,
    record_simulation_metrics,
)

logger = logging.getLogger(__name__)


def init_ray() -> None:
    """Initialize Ray connection (cluster address or local process)."""
    if ray.is_initialized():
        return
    address = (settings.RAY_ADDRESS or "local").strip().lower()
    # Windows / low-RAM hosts often fail Ray's default object-store sizing.
    object_store_memory = 100 * 1024 * 1024  # 100 MiB floor
    common = dict(
        ignore_reinit_error=True,
        num_cpus=max(1, min(settings.RAY_NUM_CPUS, 2)),
        object_store_memory=object_store_memory,
        include_dashboard=False,
    )
    if address in ("", "local", "auto", "none"):
        ray.init(**common)
        logger.info("Started local Ray runtime (object_store=%s)", object_store_memory)
    else:
        try:
            ray.init(address=settings.RAY_ADDRESS, ignore_reinit_error=True)
            logger.info(f"Connected to Ray cluster at {settings.RAY_ADDRESS}")
        except Exception as exc:
            logger.warning(
                "Ray cluster unavailable (%s); falling back to local Ray", exc
            )
            ray.init(**common)


@ray.remote
class SimulationWorker:
    """
    Ray actor for running simulations with full observability.

    Each worker loads domain packs by version and executes simulations
    with invariant checks, caching, artifact storage, and tracing.
    """

    def __init__(
        self,
        domain_pack_name: str,
        domain_pack_version: str,
        isolation_mode: str = "none",
    ):
        """Initialize worker with a domain pack."""
        self.name = domain_pack_name
        self.version = domain_pack_version
        self.pack = None
        self.invariant_checker = InvariantChecker(domain_pack_name)
        self.isolation_config = IsolationConfig(mode=IsolationMode(isolation_mode))

        # Lazy load pack
        self._load_pack()
        logger.info(
            f"Worker initialized: {domain_pack_name} v{domain_pack_version} "
            f"(isolation={isolation_mode})"
        )

    def _load_pack(self) -> None:
        """Load the domain pack (ensure packs are registered first)."""
        try:
            import compute.domain_packs  # noqa: F401 — registers Toy/Finance/Spatial
            from compute.domain_packs.sdk import DomainPackRegistry

            self.pack = DomainPackRegistry.create_instance(self.name, self.version)
        except Exception as exc:
            logger.warning(f"Failed to load pack {self.name}:{self.version}: {exc}")
            self.pack = None

    def simulate(
        self,
        state: Dict[str, Any],
        actions: Dict[str, Any],
        fidelity: str,
        seed: int,
        scenario_id: str,
        run_id: str,
        scenario_hash: str | None = None,
        store_artifacts: bool = True,
    ) -> Dict[str, Any]:
        """
        Run a single simulation with full observability.

        Returns the outcome bundle with invariant report and artifact records.
        """
        start_time = time.time()
        tracer = get_tracer()
        cache = get_result_cache()

        with tracer.trace(f"simulate:{self.name}") as span:
            span.set_tag("domain_pack", self.name)
            span.set_tag("domain_pack_version", self.version)
            span.set_tag("fidelity", fidelity)
            span.set_tag("scenario_id", scenario_id)
            span.set_tag("run_id", run_id)

            increment_active_simulations(self.name)

            try:
                # Check cache first
                effective_hash = scenario_hash
                if not effective_hash:
                    effective_hash = cache.compute_scenario_hash(
                        self.name,
                        self.version,
                        state,
                        actions,
                        fidelity,
                        seed,
                    )

                cached = cache.get(effective_hash)
                if cached:
                    record_cache_hit(self.name)
                    span.set_tag("cache_hit", True)
                    cached["cached"] = True
                    return cached

                record_cache_miss(self.name)
                span.set_tag("cache_hit", False)

                # Execute simulation
                if self.pack is None:
                    # Use isolation strategy
                    strategy = get_isolation_strategy(self.isolation_config)
                    result = strategy.execute(
                        self.name,
                        self.version,
                        state,
                        actions,
                        fidelity,
                        seed,
                        scenario_id,
                        run_id,
                    )
                else:
                    result = self._run_simulation(
                        state, actions, fidelity, seed, scenario_id, run_id
                    )

                # Run invariant checks
                if result.get("status") == "completed":
                    outcome = result.get("outcome", {})
                    invariant_report = self.invariant_checker.check_all(
                        outcome, state, actions
                    )
                    result["invariant_report"] = invariant_report.to_dict()

                    # Record violations
                    for violation in invariant_report.violations:
                        record_invariant_violation(self.name, violation.check_name)

                    span.set_tag("invariants_passed", invariant_report.passed)

                    # Store artifacts
                    if store_artifacts:
                        artifact_records = self._store_artifacts(
                            run_id, scenario_id, outcome
                        )
                        result["artifacts"] = [r.to_dict() for r in artifact_records]

                # Cache result
                cache.set(effective_hash, result)
                result["scenario_hash"] = effective_hash

                duration = time.time() - start_time
                result["runtime_seconds"] = duration
                record_simulation_metrics(
                    self.name,
                    fidelity,
                    result.get("status", "unknown"),
                    duration,
                )

                return result

            finally:
                decrement_active_simulations(self.name)

    def _run_simulation(
        self,
        state: Dict[str, Any],
        actions: Dict[str, Any],
        fidelity: str,
        seed: int,
        scenario_id: str,
        run_id: str,
    ) -> Dict[str, Any]:
        """Execute simulation using loaded pack."""
        from compute.domain_packs.sdk import Fidelity

        try:
            validated_state = self.pack.validate_state(state)
            validated_actions = self.pack.validate_actions(actions)

            feasibility = self.pack.feasibility(validated_state, validated_actions)
            if not feasibility.is_feasible:
                return {
                    "status": "failed",
                    "error": f"Infeasible configuration: {feasibility.violations}",
                    "scenario_id": scenario_id,
                    "run_id": run_id,
                }

            fidelity_enum = Fidelity(fidelity)
            outcome = self.pack.simulate(
                state=validated_state,
                actions=validated_actions,
                fidelity=fidelity_enum,
                seed=seed,
                scenario_id=scenario_id,
                run_id=run_id,
            )
            scored = self.pack.score(outcome)
            outcome_dict = outcome.model_dump()
            outcome_dict["metrics"] = [
                m.model_dump() if hasattr(m, "model_dump") else m
                for m in scored.metrics
            ]

            return {
                "status": "completed",
                "outcome": outcome_dict,
                "scenario_id": scenario_id,
                "run_id": run_id,
                "state": state,
                "actions": actions,
                "seed": seed,
                "fidelity": fidelity,
            }

        except Exception as exc:
            logger.exception(f"Simulation failed: {exc}")
            return {
                "status": "failed",
                "error": str(exc),
                "scenario_id": scenario_id,
                "run_id": run_id,
            }

    def _store_artifacts(
        self,
        run_id: str,
        scenario_id: str,
        outcome: Dict[str, Any],
    ) -> List[ArtifactRecord]:
        """Store simulation artifacts to MinIO."""
        try:
            pipeline = get_artifact_pipeline()
            records = pipeline.store_simulation_output(run_id, scenario_id, outcome)

            for record in records:
                record_artifact_size(record.content_type, record.size_bytes)

            return records
        except Exception as exc:
            logger.warning(f"Failed to store artifacts: {exc}")
            return []

    def score(
        self,
        outcome: Dict[str, Any],
        objectives: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Score a simulation outcome."""
        if self.pack is None:
            return {"error": "Pack not loaded"}

        from compute.domain_packs.sdk.types import ObjectiveSpec, OutcomeBundle

        outcome_bundle = OutcomeBundle(**outcome)
        obj_spec = ObjectiveSpec(**objectives) if objectives else None
        metrics = self.pack.score(outcome_bundle, obj_spec)
        return metrics.model_dump()

    def get_cost_estimate(self, fidelity: str) -> Dict[str, Any]:
        """Get cost estimate for a fidelity level."""
        if self.pack is None:
            return {"error": "Pack not loaded"}

        from compute.domain_packs.sdk import Fidelity

        fidelity_enum = Fidelity(fidelity)
        cost = self.pack.cost_model(fidelity_enum)
        return cost.model_dump()

    def health_check(self) -> Dict[str, Any]:
        """Check worker health."""
        return {
            "healthy": True,
            "domain_pack": self.name,
            "domain_pack_version": self.version,
            "pack_loaded": self.pack is not None,
        }


class SimulationFabric:
    """
    High-level interface for distributed simulation execution.

    Manages worker pools and orchestrates simulation runs with
    caching, artifact storage, and observability.
    """

    def __init__(self, pool_size: int = 4, isolation_mode: str = "none"):
        """Initialize the fabric."""
        init_ray()
        self._worker_pools: Dict[str, List[ray.actor.ActorHandle]] = {}
        self._default_pool_size = pool_size
        self._default_isolation_mode = isolation_mode

    def get_worker_pool(
        self,
        domain_pack_name: str,
        domain_pack_version: str,
        pool_size: int | None = None,
        isolation_mode: str | None = None,
    ) -> List[ray.actor.ActorHandle]:
        """Get or create a worker pool for a domain pack."""
        key = f"{domain_pack_name}:{domain_pack_version}"
        pool_size = pool_size or self._default_pool_size
        isolation_mode = isolation_mode or self._default_isolation_mode

        if key not in self._worker_pools:
            workers = [
                SimulationWorker.remote(
                    domain_pack_name, domain_pack_version, isolation_mode
                )
                for _ in range(pool_size)
            ]
            self._worker_pools[key] = workers
            logger.info(
                f"Created worker pool for {key} with {pool_size} workers "
                f"(isolation={isolation_mode})"
            )

        return self._worker_pools[key]

    async def run_batch(
        self,
        domain_pack_name: str,
        domain_pack_version: str,
        scenarios: List[Dict[str, Any]],
        store_artifacts: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Run a batch of simulations with caching and observability.

        Distributes work across the worker pool.
        """
        tracer = get_tracer()

        with tracer.trace("run_batch") as span:
            span.set_tag("domain_pack", domain_pack_name)
            span.set_tag("batch_size", len(scenarios))

            workers = self.get_worker_pool(domain_pack_name, domain_pack_version)

            # Submit tasks round-robin
            futures = []
            for i, scenario in enumerate(scenarios):
                worker = workers[i % len(workers)]
                future = worker.simulate.remote(
                    state=scenario.get("state", {}),
                    actions=scenario.get("actions", {}),
                    fidelity=scenario.get("fidelity", "mid"),
                    seed=scenario.get("seed", 0),
                    scenario_id=scenario.get("scenario_id", f"s-{i}"),
                    run_id=scenario.get("run_id", "unknown"),
                    scenario_hash=scenario.get("scenario_hash"),
                    store_artifacts=store_artifacts,
                )
                futures.append(future)

            # Gather results
            results = ray.get(futures)

            span.set_tag("completed", len([r for r in results if r.get("status") == "completed"]))
            span.set_tag("failed", len([r for r in results if r.get("status") == "failed"]))
            span.set_tag("cached", len([r for r in results if r.get("cached")]))

            return results

    async def run_single(
        self,
        domain_pack_name: str,
        domain_pack_version: str,
        state: Dict[str, Any],
        actions: Dict[str, Any],
        fidelity: str,
        seed: int,
        scenario_id: str,
        run_id: str,
        scenario_hash: str | None = None,
        store_artifacts: bool = True,
    ) -> Dict[str, Any]:
        """Run a single simulation."""
        workers = self.get_worker_pool(domain_pack_name, domain_pack_version)
        worker = workers[0]

        result = ray.get(
            worker.simulate.remote(
                state=state,
                actions=actions,
                fidelity=fidelity,
                seed=seed,
                scenario_id=scenario_id,
                run_id=run_id,
                scenario_hash=scenario_hash,
                store_artifacts=store_artifacts,
            )
        )
        return result

    def health_check(self) -> Dict[str, Any]:
        """Check health of all worker pools."""
        health = {"pools": {}}

        for key, workers in self._worker_pools.items():
            pool_health = []
            for worker in workers:
                try:
                    status = ray.get(worker.health_check.remote(), timeout=5)
                    pool_health.append(status)
                except Exception as exc:
                    pool_health.append({"healthy": False, "error": str(exc)})
            health["pools"][key] = pool_health

        return health

    def shutdown(self) -> None:
        """Shutdown all worker pools."""
        for key, workers in self._worker_pools.items():
            for worker in workers:
                try:
                    ray.kill(worker)
                except Exception:
                    pass
        self._worker_pools.clear()
        logger.info("Simulation fabric shut down")


# Global fabric instance
_fabric: SimulationFabric | None = None


def get_fabric() -> SimulationFabric:
    """Get the global simulation fabric instance."""
    global _fabric
    if _fabric is None:
        _fabric = SimulationFabric()
    return _fabric
