"""Optimization Loop Workflow."""
from datetime import timedelta
from typing import Any, Dict

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..activities import (
        initialize_optimizer,
        propose_next_batch,
        execute_simulation_batch,
        score_outcomes,
        update_optimizer,
        check_convergence,
        get_pareto_frontier,
    )


@workflow.defn
class OptimizationLoopWorkflow:
    """
    Iterative optimization workflow.
    
    Implements a Bayesian optimization loop:
    1. Initialize optimizer state
    2. Loop until budget exhausted or converged:
       a. Propose next batch of scenarios
       b. Execute simulations
       c. Score outcomes
       d. Update optimizer with results
       e. Check convergence
    3. Return best results and Pareto frontier
    """
    
    def __init__(self):
        self.status = "pending"
        self.iteration = 0
        self.budget_used = 0
        self.best_score = None
        self.converged = False
    
    @workflow.run
    async def run(self, run_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the optimization loop."""
        run_id = run_spec["run_id"]
        budget = run_spec.get("budget", 1000)
        batch_size = run_spec.get("batch_size", 20)
        max_iterations = budget // batch_size
        
        self.status = "initializing"
        
        # Step 1: Initialize optimizer
        optimizer_state = await workflow.execute_activity(
            initialize_optimizer,
            args=[run_spec],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        
        self.status = "optimizing"
        all_results = []
        
        # Step 2: Optimization loop
        while self.iteration < max_iterations and not self.converged:
            self.iteration += 1
            
            # Propose next batch
            scenarios = await workflow.execute_activity(
                propose_next_batch,
                args=[optimizer_state, batch_size, run_id],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            
            # Execute simulations
            outcomes = await workflow.execute_activity(
                execute_simulation_batch,
                args=[
                    run_spec["domain_pack_id"],
                    run_spec["domain_pack_version"],
                    scenarios,
                ],
                start_to_close_timeout=timedelta(minutes=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            
            # Score outcomes
            scored = await workflow.execute_activity(
                score_outcomes,
                args=[run_id, outcomes, run_spec.get("rubric_id")],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            
            all_results.extend(scored)
            self.budget_used += len(scenarios)
            
            # Update best score
            for result in scored:
                if result.get("score") is not None:
                    if self.best_score is None or result["score"] > self.best_score:
                        self.best_score = result["score"]
            
            # Update optimizer
            optimizer_state = await workflow.execute_activity(
                update_optimizer,
                args=[optimizer_state, scored],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            
            # Check convergence
            convergence_result = await workflow.execute_activity(
                check_convergence,
                args=[optimizer_state, all_results],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            
            self.converged = convergence_result.get("converged", False)
        
        self.status = "finalizing"
        
        # Get Pareto frontier if multi-objective
        pareto_frontier = None
        if run_spec.get("objectives", {}).get("type") == "multi":
            pareto_frontier = await workflow.execute_activity(
                get_pareto_frontier,
                args=[all_results, run_spec["objectives"]],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        
        self.status = "completed"
        
        return {
            "run_id": run_id,
            "status": "completed",
            "iterations": self.iteration,
            "budget_used": self.budget_used,
            "best_score": self.best_score,
            "converged": self.converged,
            "pareto_frontier": pareto_frontier,
        }
    
    @workflow.query
    def get_status(self) -> Dict[str, Any]:
        """Query current optimization status."""
        return {
            "status": self.status,
            "iteration": self.iteration,
            "budget_used": self.budget_used,
            "best_score": self.best_score,
            "converged": self.converged,
        }
    
    @workflow.signal
    def pause_optimization(self) -> None:
        """Signal to pause optimization."""
        self.status = "paused"
    
    @workflow.signal
    def resume_optimization(self) -> None:
        """Signal to resume optimization."""
        if self.status == "paused":
            self.status = "optimizing"
