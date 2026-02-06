from datetime import datetime
import uuid
from typing import AsyncIterator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db.database import AsyncSessionLocal, get_session
from services.api.db import models
from services.api.auth import get_current_user, UserContext, require_permission
from services.orchestrator.workflows.simulation_run import SimulationRunWorkflow
from temporalio.client import Client as TemporalClient

from pydantic import BaseModel, Field

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Pydantic Models for API --- #

class ObjectiveSpec(BaseModel):
    description: str
    objectives: List[dict]
    constraints: List[dict]

class RunConfig(BaseModel):
    maxScenarios: int = 100
    maxWallTime: int = 3600 # seconds
    fidelityPolicy: str = "cheap_first"

class StartRunRequest(BaseModel):
    prompt: str = Field(..., example="Find the best intervention for SpatialPack demo")
    domain_pack: str = Field(..., example="SpatialPack")
    config: RunConfig = Field(default_factory=RunConfig)
    project_id: Optional[str] = Field(None, example="proj-001")

class RunResponse(BaseModel):
    id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    status: str
    domain_pack: str
    domain_pack_version: str
    objective_spec: dict
    created_at: datetime
    updated_at: datetime
    stages: List[dict]
    counters: dict
    current_best: Optional[dict] = None
    candidates: List[dict]

    class Config:
        from_attributes = True
        json_encoders = {
            uuid.UUID: lambda u: str(u),
            datetime: lambda dt: dt.isoformat(),
        }

class RunStatusUpdate(BaseModel):
    run_id: uuid.UUID
    stage: str
    status: str
    progress: Optional[float] = None
    message: Optional[str] = None

# --- Temporal Client --- #

async def get_temporal_client() -> TemporalClient:
    # TODO: Configure Temporal client for production deployment
    return await TemporalClient.connect("localhost:7233") # Use settings.TEMPORAL_HOST later

# --- API Endpoints --- #

def _run_to_response(run: models.Run) -> dict:
    """Build RunResponse-shaped dict from Run using run_spec."""
    spec = run.run_spec or {}
    return {
        "id": run.id,
        "project_id": run.project_id,
        "status": run.status,
        "domain_pack": spec.get("domain_pack", ""),
        "domain_pack_version": spec.get("domain_pack_version", ""),
        "objective_spec": spec.get("objective_spec", {"description": "", "objectives": [], "constraints": []}),
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "stages": spec.get("stages", []),
        "counters": spec.get("counters", {}),
        "current_best": spec.get("current_best"),
        "candidates": spec.get("candidates", []),
    }


@router.post("/runs/start", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    request: StartRunRequest,
    background_tasks: BackgroundTasks,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    temporal_client: TemporalClient = Depends(get_temporal_client),
) -> RunResponse:
    """Starts a new simulation run via Temporal workflow."""
    if user.org_id is None:
        raise HTTPException(status_code=400, detail="Organization context required.")
    # 1. Validate project and domain pack
    project_id = uuid.UUID(request.project_id) if request.project_id else None
    if not project_id:
        projects = await user.get_projects(session)
        if not projects:
            raise HTTPException(status_code=400, detail="No projects found for user's organization.")
        project_id = projects[0].id

    domain_pack_record = await models.DomainPack.get_by_name(session, request.domain_pack)
    if not domain_pack_record:
        raise HTTPException(status_code=404, detail=f"Domain pack '{request.domain_pack}' not found.")

    domain_pack_version_record = await models.DomainPackVersion.get_latest_approved_version(
        session, domain_pack_record.id
    )
    if not domain_pack_version_record:
        raise HTTPException(status_code=404, detail=f"No approved version found for domain pack '{request.domain_pack}'.")

    run_spec = {
        "domain_pack": domain_pack_record.name,
        "domain_pack_version": domain_pack_version_record.version,
        "objective_spec": {
            "description": request.prompt,
            "objectives": [],
            "constraints": [],
        },
        "cost_governance": {
            "max_scenarios": request.config.maxScenarios,
            "max_wall_time": request.config.maxWallTime,
            "fidelity_policy": request.config.fidelityPolicy,
        },
        "stages": [{"stage": "formalize", "status": "pending"}],
        "counters": {
            "scenarios_proposed": 0,
            "scenarios_simulated": 0,
            "scenarios_promoted": 0,
            "cache_hits": 0,
            "compute_cost": 0.0,
            "storage_cost": 0.0,
            "budget_consumed": 0.0,
            "budget_total": 0.0,
        },
        "candidates": [],
    }

    new_run = models.Run(
        project_id=project_id,
        org_id=user.org_id,
        status="running",
        domain_pack_version_id=domain_pack_version_record.id,
        run_spec=run_spec,
    )
    session.add(new_run)
    await session.commit()
    await session.refresh(new_run)

    run_id = new_run.id

    # Build complete run_spec with run_id and org_id for workflow
    workflow_run_spec = {
        **run_spec,
        "run_id": str(run_id),
        "org_id": str(user.org_id),
        "domain_pack_id": str(domain_pack_record.id),
        "domain_pack_version_id": str(domain_pack_version_record.id),
    }

    async def start_temporal_workflow():
        try:
            await temporal_client.start_workflow(
                SimulationRunWorkflow.run,
                workflow_run_spec,  # Pass full run_spec, not just run_id
                id=str(run_id),
                task_queue="gsip-main",
            )
        except Exception as e:
            logger.error("Failed to start Temporal workflow for run %s: %s", run_id, e)
            async with AsyncSessionLocal() as s:
                await s.execute(
                    update(models.Run).where(models.Run.id == run_id).values(status="failed")
                )
                await s.commit()

    background_tasks.add_task(start_temporal_workflow)

    return RunResponse.model_validate(_run_to_response(new_run))


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> RunResponse:
    """Retrieves the current state of a simulation run."""
    if user.org_id is None:
        raise HTTPException(status_code=400, detail="Organization context required.")
    run = await models.Run.get_by_id_and_org(session, run_id, user.org_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    return RunResponse.model_validate(_run_to_response(run))


@router.get("/runs/{run_id}/stream")
async def stream_run_updates(
    run_id: uuid.UUID,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EventSourceResponse:
    """Streams live updates for a simulation run via Server-Sent Events (SSE)."""
    if user.org_id is None:
        raise HTTPException(status_code=400, detail="Organization context required.")
    run = await models.Run.get_by_id_and_org(session, run_id, user.org_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found or unauthorized.")

    async def event_generator():
        last_status_hash = ""
        last_counters_hash = ""
        last_candidates_hash = ""
        last_best_hash = ""

        while True:
            current_run = await models.Run.get_by_id_and_org(session, run_id, user.org_id)
            if not current_run:
                yield {"event": "error", "data": json.dumps("Run not found, closing stream.")}
                break

            spec = current_run.run_spec or {}
            stages = spec.get("stages", [])
            counters = spec.get("counters", {})
            candidates = spec.get("candidates", [])
            current_best = spec.get("current_best")

            current_status_hash = json.dumps(stages, sort_keys=True)
            current_counters_hash = json.dumps(counters, sort_keys=True)
            current_candidates_hash = json.dumps(candidates, sort_keys=True)
            current_best_hash = json.dumps(current_best or {}, sort_keys=True)

            if current_status_hash != last_status_hash:
                yield {"event": "stage_update", "data": json.dumps(stages[-1] if stages else {})}
                last_status_hash = current_status_hash

            if current_counters_hash != last_counters_hash:
                yield {"event": "counters_update", "data": json.dumps(counters)}
                last_counters_hash = current_counters_hash

            if current_candidates_hash != last_candidates_hash:
                yield {"event": "scenario_result", "data": json.dumps(candidates)}
                last_candidates_hash = current_candidates_hash

            if current_best_hash != last_best_hash:
                yield {"event": "best_changed", "data": json.dumps(current_best or {})}
                last_best_hash = current_best_hash

            if current_run.status in ("completed", "failed"):
                yield {"event": "run_completed", "data": json.dumps(_run_to_response(current_run))}
                break

            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.get("/runs/{run_id}/benchmarks")
async def get_run_benchmarks(
    run_id: uuid.UUID,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Retrieves benchmarks associated with a specific run."""
    if user.org_id is None:
        raise HTTPException(status_code=400, detail="Organization context required.")
    run = await models.Run.get_by_id_and_org(session, run_id, user.org_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found or unauthorized.")

    domain_pack_name = (run.run_spec or {}).get("domain_pack", "")
    if not domain_pack_name:
        return {"benchmarks": []}

    benchmarks_records = await models.Benchmark.get_all_approved_for_domain_pack(
        session, domain_pack_name
    )
    benchmarks_data = [
        {
            "id": str(b.id),
            "name": b.name,
            "metric_name": b.metric_name,
            "threshold_value": b.threshold_value,
            "threshold_type": b.threshold_type,
            "metadata": b.metadata_,
            "source_id": str(b.source_id) if b.source_id else None,
            "passed": True,
        }
        for b in benchmarks_records
    ]
    return {"benchmarks": benchmarks_data}

