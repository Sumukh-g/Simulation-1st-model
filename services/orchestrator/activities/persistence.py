"""Persistence activities for workflow progress and results."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from temporalio import activity

from ..db import get_session
from services.api.db import models


def _to_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


@activity.defn
async def update_run_status(run_id: str, status: str) -> None:
    async with get_session() as session:
        await session.execute(
            update(models.Run)
            .where(models.Run.id == _to_uuid(run_id))
            .values(status=status)
        )
        await session.commit()


@activity.defn
async def record_run_stage(run_id: str, stage: str, status: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    payload = {
        "run_id": _to_uuid(run_id),
        "stage": stage,
        "status": status,
        "started_at": now if status == "started" else None,
        "ended_at": now if status in {"completed", "failed"} else None,
    }
    async with get_session() as session:
        stage_row = models.RunStage(**payload)
        session.add(stage_row)
        await session.commit()
        await session.refresh(stage_row)
        return stage_row.to_dict()


@activity.defn
async def update_run_spec(run_id: str, run_spec: Dict[str, Any]) -> None:
    async with get_session() as session:
        await session.execute(
            update(models.Run)
            .where(models.Run.id == _to_uuid(run_id))
            .values(run_spec=run_spec)
        )
        await session.commit()


@activity.defn
async def persist_scenarios_and_instances(
    run_id: str,
    scenarios: List[Dict[str, Any]],
    instance_index: int = 0,
) -> List[Dict[str, Any]]:
    """Insert scenarios and ensure scenario instances exist."""
    run_uuid = _to_uuid(run_id)
    scenario_hashes = [scenario["scenario_hash"] for scenario in scenarios]

    async with get_session() as session:
        existing = await session.execute(
            select(models.Scenario).where(models.Scenario.scenario_hash.in_(scenario_hashes))
        )
        existing_map = {row.scenario_hash: row for row in existing.scalars().all()}

        new_rows = []
        for scenario in scenarios:
            if scenario["scenario_hash"] in existing_map:
                continue
            new_rows.append(
                {
                    "run_id": run_uuid,
                    "scenario_hash": scenario["scenario_hash"],
                    "input_state": scenario.get("state", {}),
                    "actions": scenario.get("actions", {}),
                    "fidelity": scenario.get("fidelity"),
                    "seed": scenario.get("seed"),
                }
            )

        if new_rows:
            stmt = pg_insert(models.Scenario).values(new_rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["scenario_hash"])
            await session.execute(stmt)

        refreshed = await session.execute(
            select(models.Scenario).where(models.Scenario.scenario_hash.in_(scenario_hashes))
        )
        scenario_rows = {row.scenario_hash: row for row in refreshed.scalars().all()}

        instance_rows = []
        for scenario in scenarios:
            row = scenario_rows[scenario["scenario_hash"]]
            scenario["scenario_id"] = str(row.id)
            instance_rows.append(
                {
                    "scenario_id": row.id,
                    "run_id": run_uuid,
                    "instance_index": instance_index,
                    "status": "queued",
                }
            )

        if instance_rows:
            stmt = pg_insert(models.ScenarioInstance).values(instance_rows)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["scenario_id", "instance_index"]
            )
            await session.execute(stmt)

        await session.commit()

        instances = await session.execute(
            select(models.ScenarioInstance).where(
                models.ScenarioInstance.scenario_id.in_([row.id for row in scenario_rows.values()]),
                models.ScenarioInstance.instance_index == instance_index,
            )
        )
        instance_map = {
            row.scenario_id: row for row in instances.scalars().all()
        }

        for scenario in scenarios:
            scenario_uuid = _to_uuid(scenario["scenario_id"])
            instance = instance_map.get(scenario_uuid)
            scenario["scenario_instance_id"] = str(instance.id) if instance else None

    return scenarios


@activity.defn
async def fetch_cached_outcomes(
    scenarios: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split scenarios into cached outcomes and pending scenarios."""
    if not scenarios:
        return [], []

    scenario_instance_ids = [
        _to_uuid(s.get("scenario_instance_id")) for s in scenarios if s.get("scenario_instance_id")
    ]
    if not scenario_instance_ids:
        return [], scenarios

    async with get_session() as session:
        metrics_rows = await session.execute(
            select(models.MetricResult).where(
                models.MetricResult.scenario_instance_id.in_(scenario_instance_ids)
            )
        )
        metrics_map: Dict[uuid.UUID, List[models.MetricResult]] = {}
        for row in metrics_rows.scalars().all():
            metrics_map.setdefault(row.scenario_instance_id, []).append(row)

    cached_outcomes: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []

    for scenario in scenarios:
        instance_id = _to_uuid(scenario.get("scenario_instance_id"))
        metrics = metrics_map.get(instance_id, [])
        if metrics:
            cached_outcomes.append(
                {
                    "status": "cached",
                    "scenario_id": scenario["scenario_id"],
                    "scenario_instance_id": scenario["scenario_instance_id"],
                    "run_id": scenario["run_id"],
                    "outcome": {
                        "metrics": [
                            {"name": m.metric_name, "value": m.metric_value, "unit": m.unit}
                            for m in metrics
                        ]
                    },
                }
            )
        else:
            pending.append(scenario)

    return cached_outcomes, pending


@activity.defn
async def persist_metric_results(
    scenario_instance_id: str,
    metrics: List[Dict[str, Any]],
) -> None:
    if not metrics:
        return
    instance_uuid = _to_uuid(scenario_instance_id)
    async with get_session() as session:
        existing = await session.execute(
            select(models.MetricResult.metric_name).where(
                models.MetricResult.scenario_instance_id == instance_uuid
            )
        )
        existing_names = {row[0] for row in existing.fetchall()}
        rows = [
            {
                "scenario_instance_id": instance_uuid,
                "metric_name": metric.get("name"),
                "metric_value": metric.get("value", 0.0),
                "unit": metric.get("unit"),
            }
            for metric in metrics
            if metric.get("name") not in existing_names
        ]
        if rows:
            await session.execute(pg_insert(models.MetricResult).values(rows))
        await session.commit()


@activity.defn
async def persist_uncertainty_results(
    scenario_instance_id: str,
    uncertainty: Dict[str, Any],
) -> None:
    if not uncertainty:
        return
    rows = []
    for metric_name, values in uncertainty.items():
        rows.append(
            {
                "scenario_instance_id": _to_uuid(scenario_instance_id),
                "metric_name": metric_name,
                "p50": values.get("p50"),
                "p90": values.get("p90"),
                "p95": values.get("p95"),
            }
        )
    async with get_session() as session:
        await session.execute(pg_insert(models.UncertaintyResult).values(rows))
        await session.commit()


@activity.defn
async def persist_optimizer_step(
    run_id: str,
    step_index: int,
    method: str,
    parameters: Dict[str, Any],
    metrics: Dict[str, Any],
) -> None:
    async with get_session() as session:
        await session.execute(
            pg_insert(models.OptimizerStep)
            .values(
                {
                    "run_id": _to_uuid(run_id),
                    "step_index": step_index,
                    "method": method,
                    "parameters": parameters,
                    "metrics": metrics,
                }
            )
            .on_conflict_do_nothing(index_elements=["run_id", "step_index"])
        )
        await session.commit()


@activity.defn
async def persist_judge_scores(
    run_id: str,
    rubric_version_id: str | None,
    scored: List[Dict[str, Any]],
) -> None:
    if not scored:
        return
    async with get_session() as session:
        for item in scored:
            existing = await session.execute(
                select(models.JudgeScore).where(
                    models.JudgeScore.scenario_instance_id
                    == _to_uuid(item.get("scenario_instance_id"))
                )
            )
            if existing.scalar_one_or_none():
                continue
            score_row = models.JudgeScore(
                run_id=_to_uuid(run_id),
                scenario_instance_id=_to_uuid(item.get("scenario_instance_id")),
                rubric_version_id=_to_uuid(rubric_version_id) if rubric_version_id else None,
                score=item.get("score", 0.0),
            )
            session.add(score_row)
            await session.flush()
            for breakdown in item.get("breakdown", []):
                session.add(
                    models.JudgeBreakdown(
                        judge_score_id=score_row.id,
                        metric_name=breakdown.get("metric"),
                        value=breakdown.get("value"),
                        contribution=breakdown.get("contribution"),
                        details=breakdown.get("details"),
                    )
                )
        await session.commit()


@activity.defn
async def persist_artifact(
    run_id: str,
    object_key: str,
    checksum: str,
    artifact_type: str,
    content_type: str,
    size_bytes: int | None = None,
) -> Dict[str, Any]:
    async with get_session() as session:
        artifact = models.Artifact(
            run_id=_to_uuid(run_id),
            object_key=object_key,
            checksum=checksum,
            artifact_type=artifact_type,
            content_type=content_type,
            size_bytes=size_bytes,
        )
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)
        return artifact.to_dict()


@activity.defn
async def create_evidence_pack(
    org_id: str,
    name: str,
    description: str | None,
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    async with get_session() as session:
        pack = models.EvidencePack(
            org_id=_to_uuid(org_id),
            name=name,
            description=description,
        )
        session.add(pack)
        await session.flush()
        for item in items:
            session.add(
                models.EvidencePackItem(
                    evidence_pack_id=pack.id,
                    document_id=_to_uuid(item.get("document_id")),
                    chunk_id=_to_uuid(item.get("chunk_id")),
                    relevance_score=item.get("relevance_score"),
                )
            )
        await session.commit()
        await session.refresh(pack)
        return pack.to_dict()


@activity.defn
async def select_benchmarks(domain_pack_id: str | None) -> List[Dict[str, Any]]:
    async with get_session() as session:
        stmt = select(models.Benchmark).where(models.Benchmark.status == "approved")
        if domain_pack_id:
            try:
                pack_uuid = _to_uuid(domain_pack_id)
            except ValueError:
                pack_uuid = None
            if pack_uuid:
                stmt = stmt.where(models.Benchmark.domain_pack_id == pack_uuid)
            else:
                pack = await session.execute(
                    select(models.DomainPack).where(models.DomainPack.name == domain_pack_id)
                )
                pack_row = pack.scalar_one_or_none()
                if pack_row:
                    stmt = stmt.where(models.Benchmark.domain_pack_id == pack_row.id)
        rows = await session.execute(stmt)
        return [row.to_dict() for row in rows.scalars().all()]


@activity.defn
async def persist_report_artifact(
    run_id: str,
    report_payload: Dict[str, Any],
) -> Dict[str, Any]:
    encoded = json.dumps(report_payload, sort_keys=True).encode("utf-8")
    checksum = hashlib.sha256(encoded).hexdigest()
    object_key = f"runs/{run_id}/reports/report.json"
    return await persist_artifact(
        run_id=run_id,
        object_key=object_key,
        checksum=checksum,
        artifact_type="report",
        content_type="application/json",
        size_bytes=len(encoded),
    )
