"""Simulation Run Workflow."""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any, Dict, List

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..activities import (
        formalize_objectives,
        build_evidence_pack,
        model_causes,
        generate_structured_scenarios,
        promote_finalists,
        generate_robustness_scenarios,
        initialize_optimizer,
        propose_next_batch,
        execute_simulation_batch,
        judge_score_outcomes,
        update_optimizer,
        check_convergence,
        aggregate_results,
        seal_run,
        update_run_status,
        record_run_stage,
        update_run_spec,
        persist_run_progress,
        persist_scenarios_and_instances,
        fetch_cached_outcomes,
        persist_metric_results,
        persist_optimizer_step,
        persist_judge_scores,
        create_evidence_pack,
        select_benchmarks,
        persist_report_artifact,
    )


@workflow.defn
class SimulationRunWorkflow:
    """Main workflow for orchestrating a full simulation run."""

    def __init__(self):
        self.status = "pending"
        self.completed_scenarios = 0
        self.total_scenarios = 0
        self.best_score = None
        self.stop_reason = None

    async def _set_status(self, run_id: str, status: str) -> None:
        await workflow.execute_activity(
            update_run_status,
            args=[run_id, status],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

    async def _stage(self, run_id: str, stage: str, status: str) -> None:
        await workflow.execute_activity(
            record_run_stage,
            args=[run_id, stage, status],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

    async def _save_spec(self, run_id: str, run_spec: Dict[str, Any]) -> None:
        await workflow.execute_activity(
            update_run_spec,
            args=[run_id, run_spec],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

    @workflow.run
    async def run(self, run_spec: Dict[str, Any]) -> Dict[str, Any]:
        # Extract run_id - handle both dict and string cases for backwards compatibility
        if isinstance(run_spec, str):
            run_id = run_spec
            run_spec = {"run_id": run_id}
        else:
            run_id = run_spec.get("run_id")
            if not run_id:
                raise ValueError("run_spec must contain 'run_id'")
        
        start_time = workflow.now()
        await self._set_status(run_id, "running")

        # Step 1: Formalize objective/constraints/context
        await self._stage(run_id, "formalize", "started")
        formalized = await workflow.execute_activity(
            formalize_objectives,
            args=[run_spec],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        run_spec.update(formalized)
        await self._save_spec(run_id, run_spec)
        await self._stage(run_id, "formalize", "completed")

        # Step 2: Evidence pack + benchmark selection
        await self._stage(run_id, "evidence", "started")
        evidence_request = await workflow.execute_activity(
            build_evidence_pack,
            args=[run_spec],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        evidence_pack = await workflow.execute_activity(
            create_evidence_pack,
            args=[
                run_spec["org_id"],
                evidence_request["name"],
                evidence_request.get("description"),
                evidence_request.get("items", []),
            ],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        run_spec["evidence_pack_id"] = evidence_pack["id"]
        benchmarks = await workflow.execute_activity(
            select_benchmarks,
            args=[run_spec.get("domain_pack_id")],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        await self._save_spec(run_id, run_spec)
        await self._stage(run_id, "evidence", "completed")

        # Step 3: Cause/levers modeling
        await self._stage(run_id, "cause_modeling", "started")
        cause_model = await workflow.execute_activity(
            model_causes,
            args=[run_spec],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        await self._stage(run_id, "cause_modeling", "completed")

        # Step 4: Scenario generation (structured)
        await self._stage(run_id, "scenarios", "started")
        scenarios = await workflow.execute_activity(
            generate_structured_scenarios,
            args=[run_spec],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        scenarios = await workflow.execute_activity(
            persist_scenarios_and_instances,
            args=[run_id, scenarios, 0],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        self.total_scenarios = len(scenarios)
        await self._stage(run_id, "scenarios", "completed")

        # Step 5: Optimize loop (cheap fidelity)
        await self._stage(run_id, "simulation", "started")
        await self._stage(run_id, "optimize", "started")
        optimizer_state = await workflow.execute_activity(
            initialize_optimizer,
            args=[run_spec],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        cost_limits = run_spec.get("cost_limits") or {}
        cost_gov = run_spec.get("cost_governance") or {}
        max_scenarios = int(
            cost_limits.get(
                "max_scenarios",
                cost_gov.get("max_scenarios", run_spec.get("budget", 1000)),
            )
        )
        max_wall_time = int(
            cost_limits.get(
                "max_wall_time_seconds",
                cost_gov.get("max_wall_time", 6 * 3600),
            )
        )
        max_compute_time = int(cost_limits.get("max_compute_time_seconds", 8 * 3600))
        max_storage = int(cost_limits.get("max_storage_bytes", 5_000_000_000))

        compute_time = 0.0
        storage_bytes = 0
        cache_hits = 0
        promoted_count = 0
        objectives = run_spec.get("objectives")
        all_scored: List[Dict[str, Any]] = []

        batch_size = run_spec.get("batch_size", 20)
        max_iterations = max(1, max_scenarios // batch_size)
        iteration = 0
        converged = False

        while iteration < max_iterations and not converged:
            if self.completed_scenarios >= max_scenarios:
                self.stop_reason = "max_scenarios"
                break
            if (workflow.now() - start_time).total_seconds() > max_wall_time:
                self.stop_reason = "max_wall_time"
                break
            if compute_time > max_compute_time:
                self.stop_reason = "max_compute_time"
                break
            if storage_bytes > max_storage:
                self.stop_reason = "max_storage"
                break

            iteration += 1
            batch = await workflow.execute_activity(
                propose_next_batch,
                args=[optimizer_state, batch_size, run_id],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            batch = self._enforce_fidelity(batch, "cheap")
            batch = self._rehash_scenarios(batch)
            batch = await workflow.execute_activity(
                persist_scenarios_and_instances,
                args=[run_id, batch, 0],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            cached, pending = await workflow.execute_activity(
                fetch_cached_outcomes,
                args=[batch],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            cache_hits += len(cached)
            outcomes: List[Dict[str, Any]] = list(cached)
            if pending:
                new_outcomes = await workflow.execute_activity(
                    execute_simulation_batch,
                    args=[
                        run_spec.get("domain_pack") or run_spec["domain_pack_id"],
                        run_spec["domain_pack_version"],
                        pending,
                    ],
                    start_to_close_timeout=timedelta(minutes=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                outcomes.extend(self._attach_instance_ids(new_outcomes, pending))

            for outcome in outcomes:
                metrics = outcome.get("outcome", {}).get("metrics", [])
                if metrics and outcome.get("scenario_instance_id"):
                    await workflow.execute_activity(
                        persist_metric_results,
                        args=[outcome["scenario_instance_id"], metrics],
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                compute_time += self._estimate_compute_time(outcome)
                storage_bytes += self._estimate_storage(outcome)

            scored = await workflow.execute_activity(
                judge_score_outcomes,
                args=[
                    run_id,
                    outcomes,
                    run_spec.get("rubric_version_id"),
                    run_spec.get("rubric_id"),
                    benchmarks,
                    objectives,
                ],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            all_scored.extend(scored)
            await workflow.execute_activity(
                persist_judge_scores,
                args=[run_id, run_spec.get("rubric_version_id"), scored],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            optimizer_state = await workflow.execute_activity(
                update_optimizer,
                args=[optimizer_state, scored],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            await workflow.execute_activity(
                persist_optimizer_step,
                args=[
                    run_id,
                    iteration,
                    optimizer_state.get("optimizer_type", "bayesian"),
                    {"batch_size": batch_size},
                    {"best_score": optimizer_state.get("best_score")},
                ],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            convergence = await workflow.execute_activity(
                check_convergence,
                args=[optimizer_state, all_scored],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            converged = convergence.get("converged", False)
            batch_success = sum(
                1
                for row in scored
                if row.get("score") is not None
                and (row.get("outcome") or {}).get("metrics")
            )
            self.completed_scenarios += batch_success

            if batch_success == 0 and not all_scored and iteration >= 2:
                self.stop_reason = "all_simulations_failed"
                break

        await self._stage(run_id, "optimize", "completed")
        await self._stage(run_id, "simulation", "completed")
        if converged and not self.stop_reason:
            self.stop_reason = convergence.get("reason", "converged")
        if iteration >= max_iterations and not self.stop_reason:
            self.stop_reason = "max_iterations"

        # Step 6: Promote finalists to mid/high fidelity + replicates.
        # Finalization runs whenever we have finalists; the loop always stops
        # with a stop_reason, so gating on "not stop_reason" would skip it.
        finalists = self._select_top_scenarios(all_scored, run_spec.get("finalist_count", 5))
        promoted_count = len(finalists)
        if finalists:
            await self._stage(run_id, "promote_finalists", "started")
            mid = await workflow.execute_activity(
                promote_finalists,
                args=[finalists, "mid", run_spec.get("replicates", 3)],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            high = await workflow.execute_activity(
                promote_finalists,
                args=[finalists, "high", run_spec.get("replicates", 3)],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            promoted = mid + high
            promoted = await workflow.execute_activity(
                persist_scenarios_and_instances,
                args=[run_id, promoted, 0],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            cached_promoted, pending_promoted = await workflow.execute_activity(
                fetch_cached_outcomes,
                args=[promoted],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            outcomes = list(cached_promoted)
            if pending_promoted:
                new_outcomes = await workflow.execute_activity(
                    execute_simulation_batch,
                    args=[
                        run_spec.get("domain_pack") or run_spec["domain_pack_id"],
                        run_spec["domain_pack_version"],
                        pending_promoted,
                    ],
                    start_to_close_timeout=timedelta(minutes=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                outcomes.extend(self._attach_instance_ids(new_outcomes, pending_promoted))
            for outcome in outcomes:
                metrics = outcome.get("outcome", {}).get("metrics", [])
                if metrics and outcome.get("scenario_instance_id"):
                    await workflow.execute_activity(
                        persist_metric_results,
                        args=[outcome["scenario_instance_id"], metrics],
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
            scored_finalists = await workflow.execute_activity(
                judge_score_outcomes,
                args=[
                    run_id,
                    outcomes,
                    run_spec.get("rubric_version_id"),
                    run_spec.get("rubric_id"),
                    benchmarks,
                    objectives,
                ],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            all_scored.extend(scored_finalists)
            await workflow.execute_activity(
                persist_judge_scores,
                args=[run_id, run_spec.get("rubric_version_id"), scored_finalists],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            await self._stage(run_id, "promote_finalists", "completed")

        # Step 7: Robustness tests
        if finalists:
            await self._stage(run_id, "robustness", "started")
            robustness = await workflow.execute_activity(
                generate_robustness_scenarios,
                args=[finalists, run_spec.get("action_ranges", {})],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            robustness = await workflow.execute_activity(
                persist_scenarios_and_instances,
                args=[run_id, robustness, 0],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            cached_robustness, pending_robustness = await workflow.execute_activity(
                fetch_cached_outcomes,
                args=[robustness],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            robustness_outcomes = list(cached_robustness)
            if pending_robustness:
                new_outcomes = await workflow.execute_activity(
                    execute_simulation_batch,
                    args=[
                        run_spec.get("domain_pack") or run_spec["domain_pack_id"],
                        run_spec["domain_pack_version"],
                        pending_robustness,
                    ],
                    start_to_close_timeout=timedelta(minutes=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                robustness_outcomes.extend(
                    self._attach_instance_ids(new_outcomes, pending_robustness)
                )
            for outcome in robustness_outcomes:
                metrics = outcome.get("outcome", {}).get("metrics", [])
                if metrics and outcome.get("scenario_instance_id"):
                    await workflow.execute_activity(
                        persist_metric_results,
                        args=[outcome["scenario_instance_id"], metrics],
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
            robustness_scored = await workflow.execute_activity(
                judge_score_outcomes,
                args=[
                    run_id,
                    robustness_outcomes,
                    run_spec.get("rubric_version_id"),
                    run_spec.get("rubric_id"),
                    benchmarks,
                    objectives,
                ],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            all_scored.extend(robustness_scored)
            await workflow.execute_activity(
                persist_judge_scores,
                args=[run_id, run_spec.get("rubric_version_id"), robustness_scored],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            await self._stage(run_id, "robustness", "completed")

        # Step 8: Deterministic scoring aggregation
        await self._stage(run_id, "judge", "started")
        summary = await workflow.execute_activity(
            aggregate_results,
            args=[run_id, all_scored, run_spec.get("objectives")],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        self.best_score = summary.get("best_score")

        # Surface counters, ranked candidates and current_best into run_spec so
        # the API/UI actually show results for a completed run.
        await workflow.execute_activity(
            persist_run_progress,
            args=[
                run_id,
                all_scored,
                summary,
                {
                    "scenarios_proposed": self.total_scenarios + self.completed_scenarios,
                    "scenarios_promoted": promoted_count,
                    "cache_hits": cache_hits,
                    "compute_cost": compute_time,
                    "storage_cost": float(storage_bytes),
                    "budget_consumed": int(summary.get("completed") or self.completed_scenarios),
                    "budget_total": max_scenarios,
                },
                objectives,
            ],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        completed_count = int(summary.get("completed") or 0)
        if completed_count == 0:
            spec_patch = dict(run_spec)
            spec_patch["error"] = (
                "All simulations failed or produced no scored scenarios. "
                "Check action schemas — only numeric levers are supported for optimization."
            )
            await self._save_spec(run_id, spec_patch)
            await self._stage(run_id, "simulation", "failed")
            await self._stage(run_id, "optimize", "failed")
            await self._stage(run_id, "report", "failed")
            await self._set_status(run_id, "failed")
            self.status = "failed"
            await self._stage(run_id, "judge", "failed")
            return {
                "run_id": run_id,
                "status": "failed",
                "error": spec_patch["error"],
                "summary": summary,
            }

        await self._stage(run_id, "judge", "completed")

        # Step 9: Report assembly and artifact
        await self._stage(run_id, "report", "started")
        report_payload = {
            "run_id": run_id,
            "evidence_pack_id": run_spec.get("evidence_pack_id"),
            "benchmarks": benchmarks,
            "summary": summary,
            "stop_reason": self.stop_reason,
            "cause_model": cause_model,
        }
        report_artifact = await workflow.execute_activity(
            persist_report_artifact,
            args=[run_id, report_payload],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        await self._stage(run_id, "report", "completed")

        await workflow.execute_activity(
            seal_run,
            args=[run_id],
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        await self._set_status(run_id, "completed")
        self.status = "completed"

        return {
            "run_id": run_id,
            "status": "completed",
            "total_scenarios": self.total_scenarios,
            "completed_scenarios": self.completed_scenarios,
            "best_score": self.best_score,
            "summary": summary,
            "report_artifact": report_artifact,
        }

    def _enforce_fidelity(self, scenarios: List[Dict[str, Any]], fidelity: str) -> List[Dict[str, Any]]:
        for scenario in scenarios:
            scenario["fidelity"] = fidelity
        return scenarios

    def _rehash_scenarios(self, scenarios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for scenario in scenarios:
            hash_data = {
                "run_id": scenario.get("run_id"),
                "state": scenario.get("state", {}),
                "actions": scenario.get("actions", {}),
                "seed": scenario.get("seed"),
                "fidelity": scenario.get("fidelity"),
            }
            scenario["scenario_hash"] = hashlib.sha256(
                json.dumps(hash_data, sort_keys=True).encode()
            ).hexdigest()
        return scenarios

    def _attach_instance_ids(
        self,
        outcomes: List[Dict[str, Any]],
        scenarios: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        scenario_map = {s["scenario_id"]: s for s in scenarios}
        for outcome in outcomes:
            scenario_id = outcome.get("scenario_id")
            if scenario_id in scenario_map:
                scenario = scenario_map[scenario_id]
                outcome["scenario_instance_id"] = scenario.get("scenario_instance_id")
                outcome.setdefault("state", scenario.get("state"))
                outcome.setdefault("actions", scenario.get("actions"))
                outcome.setdefault("seed", scenario.get("seed"))
        return outcomes

    def _estimate_compute_time(self, outcome: Dict[str, Any]) -> float:
        outcome_data = outcome.get("outcome", {})
        return float(outcome_data.get("runtime_seconds", 0.0))

    def _estimate_storage(self, outcome: Dict[str, Any]) -> int:
        try:
            return len(json.dumps(outcome).encode("utf-8"))
        except Exception:
            return 0

    def _select_top_scenarios(self, scored: List[Dict[str, Any]], count: int) -> List[Dict[str, Any]]:
        ranked = sorted(
            [s for s in scored if s.get("score") is not None],
            key=lambda item: item.get("score", 0.0),
            reverse=True,
        )
        selected = []
        for item in ranked[:count]:
            selected.append(
                {
                    "run_id": item["run_id"],
                    "scenario_id": item.get("scenario_id"),
                    "state": item.get("state") or item.get("outcome", {}).get("state", {}),
                    "actions": item.get("actions") or item.get("outcome", {}).get("actions", {}),
                    "seed": item.get("seed") or item.get("outcome", {}).get("seed", 0),
                }
            )
        return selected

    @workflow.query
    def get_status(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "completed_scenarios": self.completed_scenarios,
            "total_scenarios": self.total_scenarios,
            "best_score": self.best_score,
            "stop_reason": self.stop_reason,
        }

    @workflow.signal
    def cancel_run(self) -> None:
        self.status = "cancelled"
