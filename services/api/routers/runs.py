from datetime import datetime
import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from services.api.db.database import AsyncSessionLocal, get_session
from services.api.db import models
from services.api.auth import get_current_user, UserContext
from services.orchestrator.workflows.simulation_run import SimulationRunWorkflow
from temporalio.client import Client as TemporalClient

from pydantic import BaseModel, Field, model_validator

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

SimulationMode = Literal["domain_pack", "create_pack", "no_pack"]


class ObjectiveSpec(BaseModel):
    description: str
    objectives: List[dict]
    constraints: List[dict]


class RunConfig(BaseModel):
    maxScenarios: int = 100
    maxWallTime: int = 3600  # seconds
    fidelityPolicy: str = "cheap_first"


class StartRunRequest(BaseModel):
    prompt: str = Field(..., example="Move closer to the target")
    simulation_mode: SimulationMode = Field(
        default="domain_pack",
        description="domain_pack | create_pack | no_pack",
    )
    domain_pack: Optional[str] = Field(
        None, example="toy-pack", description="Required when simulation_mode=domain_pack"
    )
    config: RunConfig = Field(default_factory=RunConfig)
    project_id: Optional[str] = Field(None, example="proj-001")

    @model_validator(mode="after")
    def validate_pack_for_mode(self) -> "StartRunRequest":
        if self.simulation_mode == "domain_pack" and not self.domain_pack:
            raise ValueError("domain_pack is required when simulation_mode is domain_pack")
        return self


class RunResponse(BaseModel):
    id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    status: str
    title: str = ""
    domain_pack: str
    domain_pack_version: str
    simulation_mode: str = "domain_pack"
    objective_spec: dict
    created_at: datetime
    updated_at: datetime
    stages: List[dict]
    counters: dict
    current_best: Optional[dict] = None
    candidates: List[dict]
    narrative: Optional[dict] = None
    summary: Optional[dict] = None
    assistant_message: Optional[str] = None
    classification: Optional[dict] = None
    candidate_methods: Optional[List[dict]] = None
    draft_pack: Optional[dict] = None
    mode_status: Optional[str] = None

    class Config:
        from_attributes = True
        json_encoders = {
            uuid.UUID: lambda u: str(u),
            datetime: lambda dt: dt.isoformat(),
        }


class RunListItem(BaseModel):
    id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    status: str
    title: str
    prompt_preview: str
    domain_pack: str
    simulation_mode: str = "domain_pack"
    created_at: datetime
    updated_at: datetime


class RunListResponse(BaseModel):
    runs: List[RunListItem]
    total: int


class UpdateRunRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=200)


class ProjectItem(BaseModel):
    id: uuid.UUID
    name: str
    org_id: uuid.UUID
    description: Optional[str] = None


class ProjectListResponse(BaseModel):
    projects: List[ProjectItem]


class RunStatusUpdate(BaseModel):
    run_id: uuid.UUID
    stage: str
    status: str
    progress: Optional[float] = None
    message: Optional[str] = None


async def get_temporal_client() -> TemporalClient:
    return await TemporalClient.connect("localhost:7233")


def _prompt_from_spec(spec: dict) -> str:
    obj = spec.get("objective_spec") or {}
    if isinstance(obj, dict):
        return (obj.get("description") or "").strip()
    return ""


def _title_from_spec(spec: dict) -> str:
    title = (spec.get("title") or "").strip()
    if title:
        return title
    prompt = _prompt_from_spec(spec)
    if not prompt:
        return "Untitled run"
    return prompt if len(prompt) <= 80 else prompt[:77] + "..."


def _run_to_response(run: models.Run) -> dict:
    """Build RunResponse-shaped dict from Run using run_spec."""
    spec = run.run_spec or {}
    return {
        "id": run.id,
        "project_id": run.project_id,
        "status": run.status,
        "title": _title_from_spec(spec),
        "domain_pack": spec.get("domain_pack", "") or "",
        "domain_pack_version": spec.get("domain_pack_version", "") or "",
        "simulation_mode": spec.get("simulation_mode", "domain_pack"),
        "objective_spec": spec.get(
            "objective_spec", {"description": "", "objectives": [], "constraints": []}
        ),
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "stages": spec.get("stages", []),
        "counters": spec.get("counters", {}),
        "current_best": spec.get("current_best"),
        "candidates": spec.get("candidates", []),
        "narrative": spec.get("narrative"),
        "summary": spec.get("summary"),
        "assistant_message": spec.get("assistant_message") or spec.get("mode_message"),
        "classification": spec.get("classification"),
        "candidate_methods": spec.get("candidate_methods"),
        "draft_pack": spec.get("draft_pack") or spec.get("ephemeral_pack"),
        "mode_status": spec.get("mode_status"),
    }


def _run_to_list_item(run: models.Run) -> dict:
    spec = run.run_spec or {}
    prompt = _prompt_from_spec(spec)
    return {
        "id": run.id,
        "project_id": run.project_id,
        "status": run.status,
        "title": _title_from_spec(spec),
        "prompt_preview": prompt if len(prompt) <= 140 else prompt[:137] + "...",
        "domain_pack": spec.get("domain_pack", "") or "",
        "simulation_mode": spec.get("simulation_mode", "domain_pack"),
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


def _empty_counters() -> dict:
    return {
        "scenarios_proposed": 0,
        "scenarios_simulated": 0,
        "scenarios_promoted": 0,
        "cache_hits": 0,
        "compute_cost": 0.0,
        "storage_cost": 0.0,
        "budget_consumed": 0.0,
        "budget_total": 0.0,
    }


def _normalize_pack_name(name: str) -> str:
    """Map ToyPack / FinancePack display names to registry ids."""
    if not name:
        return name
    if name.endswith("Pack") and "-" not in name:
        return name[:-4].lower() + "-pack"
    return name


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

    project_id = uuid.UUID(request.project_id) if request.project_id else None
    if not project_id:
        projects = await user.get_projects(session)
        if not projects:
            raise HTTPException(
                status_code=400,
                detail="No projects found for user's organization. Run: python scripts/seed_data.py",
            )
        project_id = projects[0].id

    mode = request.simulation_mode
    domain_pack_record = None
    domain_pack_version_record = None

    if mode == "domain_pack":
        pack_name = _normalize_pack_name(request.domain_pack or "")
        domain_pack_record = await models.DomainPack.get_by_name(session, pack_name)
        if not domain_pack_record and request.domain_pack:
            domain_pack_record = await models.DomainPack.get_by_name(
                session, request.domain_pack
            )
        if not domain_pack_record:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Domain pack '{request.domain_pack}' not found. "
                    "Use toy-pack, finance-pack, or spatial-pack — "
                    "or choose simulation_mode=create_pack / no_pack."
                ),
            )
        domain_pack_version_record = (
            await models.DomainPackVersion.get_latest_approved_version(
                session, domain_pack_record.id
            )
        )
        if not domain_pack_version_record:
            raise HTTPException(
                status_code=404,
                detail=f"No approved version found for domain pack '{request.domain_pack}'.",
            )

    pack_name = domain_pack_record.name if domain_pack_record else ""
    pack_version = domain_pack_version_record.version if domain_pack_version_record else ""

    if mode == "create_pack":
        stages = [
            {"stage": "classify", "status": "pending"},
            {"stage": "candidate_methods", "status": "pending"},
            {"stage": "awaiting_method_selection", "status": "pending"},
        ]
    elif mode == "no_pack":
        stages = [{"stage": "ai_defined_simulation", "status": "pending"}]
    else:
        # Match the pipeline stages the workflow reports and the web UI renders.
        stages = [
            {"stage": name, "status": "pending"}
            for name in (
                "formalize",
                "evidence",
                "scenarios",
                "simulation",
                "optimize",
                "robustness",
                "judge",
                "report",
            )
        ]

    prompt = request.prompt.strip()
    title = prompt if len(prompt) <= 80 else prompt[:77] + "..."

    run_spec = {
        "simulation_mode": mode,
        "domain_pack": pack_name,
        "domain_pack_version": pack_version,
        "title": title,
        "objective_spec": {
            "description": prompt,
            "objectives": [],
            "constraints": [],
        },
        "cost_governance": {
            "max_scenarios": request.config.maxScenarios,
            "max_wall_time": request.config.maxWallTime,
            "fidelity_policy": request.config.fidelityPolicy,
        },
        "cost_limits": {
            "max_scenarios": request.config.maxScenarios,
            "max_wall_time_seconds": request.config.maxWallTime,
        },
        "stages": stages,
        "counters": _empty_counters(),
        "candidates": [],
    }

    if mode in ("create_pack", "no_pack"):
        from services.orchestrator.activities import pack_creation

        if mode == "create_pack":
            bootstrap = await asyncio.to_thread(pack_creation.bootstrap_create_pack, prompt)
        else:
            bootstrap = await asyncio.to_thread(pack_creation.bootstrap_no_pack, prompt)

        run_spec["classification"] = {
            "domain": bootstrap.get("domain"),
            "problem_type": bootstrap.get("problem_type"),
            "summary": bootstrap.get("summary"),
        }
        run_spec["candidate_methods"] = bootstrap.get("candidate_methods") or []
        run_spec["recommended_method_id"] = bootstrap.get("recommended_method_id")
        run_spec["generated_by"] = bootstrap.get("generated_by")
        if mode == "no_pack":
            run_spec["ai_simulation_spec"] = bootstrap.get("ai_simulation_spec")

        if bootstrap.get("objectives"):
            run_spec["objective_spec"] = {
                "description": prompt,
                "objectives": [
                    {
                        "name": o.get("name"),
                        "direction": o.get("direction", "maximize"),
                        "weight": 1.0,
                    }
                    for o in bootstrap["objectives"]
                    if isinstance(o, dict) and o.get("name")
                ],
                "constraints": [
                    {"name": c.get("name"), "type": c.get("type", "soft")}
                    for c in (bootstrap.get("constraints") or [])
                    if isinstance(c, dict) and c.get("name")
                ],
            }

        exec_fields = pack_creation.materialize_for_execution(
            bootstrap=bootstrap, mode=mode, prompt=prompt
        )
        run_spec.update(exec_fields)
        run_spec["scenario_budget"] = min(request.config.maxScenarios, 50)
        run_spec["budget"] = min(request.config.maxScenarios, 50)
        pack_name = run_spec["domain_pack"]
        pack_version = run_spec["domain_pack_version"]

    new_run = models.Run(
        project_id=project_id,
        org_id=user.org_id,
        status="running",
        domain_pack_version_id=(
            domain_pack_version_record.id if domain_pack_version_record else None
        ),
        run_spec=run_spec,
    )
    session.add(new_run)
    await session.commit()
    await session.refresh(new_run)

    run_id = new_run.id

    workflow_run_spec = {
        **run_spec,
        "run_id": str(run_id),
        "org_id": str(user.org_id),
        "domain_pack_id": pack_name or run_spec.get("domain_pack", ""),
        "domain_pack_version": pack_version or run_spec.get("domain_pack_version", ""),
    }
    if domain_pack_version_record:
        workflow_run_spec["domain_pack_version_id"] = str(domain_pack_version_record.id)
    if domain_pack_record:
        workflow_run_spec["domain_pack_db_id"] = str(domain_pack_record.id)

    async def _mark_run_failed(error: str) -> None:
        async with AsyncSessionLocal() as s:
            run = await s.get(models.Run, run_id)
            if run and run.status not in ("completed",):
                run.status = "failed"
                spec = dict(run.run_spec or {})
                spec["error"] = error
                run.run_spec = spec
                await s.commit()

    async def start_temporal_workflow():
        try:
            handle = await temporal_client.start_workflow(
                SimulationRunWorkflow.run,
                workflow_run_spec,
                id=str(run_id),
                task_queue="gsip-main",
            )
        except Exception as e:
            logger.error("Failed to start Temporal workflow for run %s: %s", run_id, e)
            await _mark_run_failed(str(e))
            return

        # Await completion so a mid-run activity failure surfaces as a terminal
        # run status instead of leaving the run stuck on "running" forever.
        try:
            await handle.result()
        except Exception as e:
            logger.error("Temporal workflow for run %s failed: %s", run_id, e)
            await _mark_run_failed(str(e))

    background_tasks.add_task(start_temporal_workflow)
    return RunResponse.model_validate(_run_to_response(new_run))


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProjectListResponse:
    """List projects for the current user's organization."""
    if user.org_id is None:
        raise HTTPException(status_code=400, detail="Organization context required.")
    projects = await user.get_projects(session)
    return ProjectListResponse(
        projects=[
            ProjectItem(
                id=p.id,
                name=p.name,
                org_id=p.org_id,
                description=p.description,
            )
            for p in projects
        ]
    )


@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    project_id: Optional[uuid.UUID] = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunListResponse:
    """List past runs for the current organization (newest first)."""
    if user.org_id is None:
        raise HTTPException(status_code=400, detail="Organization context required.")
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    runs = await models.Run.list_for_org(
        session,
        user.org_id,
        project_id=project_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    items = [RunListItem.model_validate(_run_to_list_item(r)) for r in runs]
    return RunListResponse(runs=items, total=len(items))


@router.patch("/runs/{run_id}", response_model=RunResponse)
async def update_run(
    run_id: uuid.UUID,
    request: UpdateRunRequest,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    """Rename a run (stores title in run_spec)."""
    if user.org_id is None:
        raise HTTPException(status_code=400, detail="Organization context required.")
    run = await models.Run.get_by_id_and_org(session, run_id, user.org_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    if request.title is None:
        raise HTTPException(status_code=400, detail="No updates provided.")
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty.")
    spec = dict(run.run_spec or {})
    spec["title"] = title
    run.run_spec = spec
    flag_modified(run, "run_spec")
    await session.commit()
    await session.refresh(run)
    return RunResponse.model_validate(_run_to_response(run))


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(
    run_id: uuid.UUID,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Archive a run so it no longer appears in history (soft delete)."""
    if user.org_id is None:
        raise HTTPException(status_code=400, detail="Organization context required.")
    run = await models.Run.get_by_id_and_org(session, run_id, user.org_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    run.status = "archived"
    spec = dict(run.run_spec or {})
    spec["archived_at"] = datetime.utcnow().isoformat() + "Z"
    run.run_spec = spec
    flag_modified(run, "run_spec")
    await session.commit()


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
) -> EventSourceResponse:
    """Streams live updates for a simulation run via Server-Sent Events (SSE)."""
    if user.org_id is None:
        raise HTTPException(status_code=400, detail="Organization context required.")

    org_id = user.org_id

    # Authz check in a short-lived session that is released *before* the stream
    # starts. Holding a Depends(get_session) connection open for the whole SSE
    # lifetime exhausted Postgres under reconnect storms.
    async with AsyncSessionLocal() as session:
        run = await models.Run.get_by_id_and_org(session, run_id, org_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found or unauthorized.")

    async def event_generator():
        # Track the last-seen status per stage so we emit *every* transition,
        # even when several stages advance within a single poll interval. A
        # single "last stage" snapshot would silently drop intermediate
        # transitions and leave the UI pipeline out of sync.
        last_stage_status: dict[str, str] = {}
        last_counters_hash = ""
        last_candidates_hash = ""
        last_best_hash = ""

        # Safety cap: never let a server-side stream run forever if a run gets
        # stuck without reaching a terminal status. 2h at a 1s interval.
        max_iterations = 7200

        # One long-lived session for the whole stream. rollback()+expire_all()
        # clears the identity map so we see commits from the orchestrator.
        async with AsyncSessionLocal() as poll_session:
            for _ in range(max_iterations):
                try:
                    await poll_session.rollback()
                    poll_session.expire_all()
                    current_run = await models.Run.get_by_id_and_org(
                        poll_session, run_id, org_id
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("SSE poll failed for run %s: %s", run_id, exc)
                    yield {
                        "event": "error",
                        "data": json.dumps("Stream temporarily unavailable"),
                    }
                    await asyncio.sleep(2)
                    continue

                if not current_run:
                    yield {
                        "event": "error",
                        "data": json.dumps("Run not found, closing stream."),
                    }
                    break

                spec = dict(current_run.run_spec or {})
                run_status = current_run.status
                response_snapshot = _run_to_response(current_run)

                stages = spec.get("stages", [])
                counters = spec.get("counters", {})
                candidates = spec.get("candidates", [])
                current_best = spec.get("current_best")

                for stage in stages:
                    if not isinstance(stage, dict):
                        continue
                    name = stage.get("stage")
                    stage_status = stage.get("status")
                    if name is None:
                        continue
                    if last_stage_status.get(name) != stage_status:
                        yield {"event": "stage_update", "data": json.dumps(stage)}
                        last_stage_status[name] = stage_status

                current_counters_hash = json.dumps(counters, sort_keys=True)
                current_candidates_hash = json.dumps(candidates, sort_keys=True)
                current_best_hash = json.dumps(current_best or {}, sort_keys=True)

                if current_counters_hash != last_counters_hash:
                    yield {"event": "counters_update", "data": json.dumps(counters)}
                    last_counters_hash = current_counters_hash

                if current_candidates_hash != last_candidates_hash:
                    yield {"event": "scenario_result", "data": json.dumps(candidates)}
                    last_candidates_hash = current_candidates_hash

                if current_best_hash != last_best_hash:
                    yield {
                        "event": "best_changed",
                        "data": json.dumps(current_best or {}),
                    }
                    last_best_hash = current_best_hash

                if run_status in ("completed", "failed", "awaiting_input"):
                    yield {
                        "event": "run_completed",
                        "data": json.dumps(response_snapshot, default=str),
                    }
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
    benchmarks_data = []
    for b in benchmarks_records:
        meta = b.metadata_ or {}
        benchmarks_data.append(
            {
                "id": str(b.id),
                "name": b.name,
                "metric_name": b.metric_name,
                "threshold_value": b.threshold_value,
                "threshold_type": b.threshold_type,
                "metadata": b.metadata_,
                "source_id": str(b.source_id) if b.source_id else None,
                "credibility_weight": meta.get("credibility_weight", 1.0),
                "context_tags": meta.get("context_tags", []),
                # Pass/fail is only known once the judge compares run results to
                # the threshold. This endpoint lists the applicable benchmarks;
                # it does not fabricate a verdict.
                "passed": None,
            }
        )
    return {"benchmarks": benchmarks_data}
