"""Temporal Worker for GSIP Orchestrator."""
import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from services.common import llm

from .config import settings
from .workflows import SimulationRunWorkflow, OptimizationLoopWorkflow
from .activities import (
    generate_scenarios,
    execute_simulation_batch,
    score_outcomes,
    judge_score_outcomes,
    aggregate_results,
    seal_run,
    initialize_optimizer,
    propose_next_batch,
    update_optimizer,
    check_convergence,
    get_pareto_frontier,
    formalize_objectives,
    build_evidence_pack,
    model_causes,
    generate_structured_scenarios,
    promote_finalists,
    generate_robustness_scenarios,
    update_run_status,
    record_run_stage,
    update_run_spec,
    persist_run_progress,
    persist_scenarios_and_instances,
    fetch_cached_outcomes,
    persist_metric_results,
    persist_uncertainty_results,
    persist_optimizer_step,
    persist_judge_scores,
    persist_artifact,
    create_evidence_pack,
    select_benchmarks,
    persist_report_artifact,
)

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger(__name__)


async def main():
    """Run the Temporal worker."""
    # Warm the LLM circuit breaker so the first run never stalls on a dead
    # provider. Runs in a thread to avoid blocking the event loop.
    try:
        status = await asyncio.to_thread(llm.preflight)
        logger.info("LLM providers: %s", status)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM preflight skipped: %s", exc)

    logger.info(f"Connecting to Temporal at {settings.TEMPORAL_HOST}")
    
    client = await Client.connect(settings.TEMPORAL_HOST)
    
    logger.info(f"Starting worker on task queue: {settings.TEMPORAL_TASK_QUEUE}")
    
    worker = Worker(
        client,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
        workflows=[
            SimulationRunWorkflow,
            OptimizationLoopWorkflow,
        ],
        activities=[
            generate_scenarios,
            execute_simulation_batch,
            score_outcomes,
            judge_score_outcomes,
            aggregate_results,
            seal_run,
            initialize_optimizer,
            propose_next_batch,
            update_optimizer,
            check_convergence,
            get_pareto_frontier,
            formalize_objectives,
            build_evidence_pack,
            model_causes,
            generate_structured_scenarios,
            promote_finalists,
            generate_robustness_scenarios,
            update_run_status,
            record_run_stage,
            update_run_spec,
            persist_run_progress,
            persist_scenarios_and_instances,
            fetch_cached_outcomes,
            persist_metric_results,
            persist_uncertainty_results,
            persist_optimizer_step,
            persist_judge_scores,
            persist_artifact,
            create_evidence_pack,
            select_benchmarks,
            persist_report_artifact,
        ],
    )
    
    logger.info("Worker started. Waiting for tasks...")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
