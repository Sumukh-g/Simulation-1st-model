"""Persistence activities for workflow progress and results."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm.attributes import flag_modified
from temporalio import activity

from ..db import get_session
from services.api.db import models

logger = logging.getLogger(__name__)


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

        # Keep run_spec.stages in sync so API/SSE clients see progress.
        run = await session.get(models.Run, _to_uuid(run_id))
        if run is not None:
            spec = dict(run.run_spec or {})
            stages = list(spec.get("stages") or [])
            updated = False
            for item in stages:
                if item.get("stage") == stage:
                    item["status"] = status
                    updated = True
                    break
            if not updated:
                stages.append({"stage": stage, "status": status})
            spec["stages"] = stages
            run.run_spec = spec
            # Plain JSONB column: in-place edits to shared nested dicts are not
            # detected by SQLAlchemy's equality check, so force the UPDATE.
            flag_modified(run, "run_spec")

        await session.commit()
        await session.refresh(stage_row)
        return stage_row.to_dict()


# Progress fields are owned by record_run_stage / persist_run_progress. The
# workflow keeps an in-memory run_spec copy whose stages/counters are stale, so
# update_run_spec must not overwrite these when it flushes objective data.
_PROGRESS_KEYS = ("stages", "counters", "candidates", "current_best")


@activity.defn
async def update_run_spec(run_id: str, run_spec: Dict[str, Any]) -> None:
    async with get_session() as session:
        run = await session.get(models.Run, _to_uuid(run_id))
        if run is None:
            return
        merged = dict(run_spec or {})
        existing = run.run_spec or {}
        for key in _PROGRESS_KEYS:
            if key in existing and existing.get(key) not in (None, [], {}):
                merged[key] = existing[key]
        run.run_spec = merged
        flag_modified(run, "run_spec")
        await session.commit()


def _template_narrative(
    objectives: Optional[Dict[str, Any]],
    current_best: Optional[Dict[str, Any]],
    summary: Dict[str, Any],
) -> str:
    """Deterministic, always-available plain-language summary (no LLM needed)."""
    n = int(summary.get("completed") or 0)
    if not current_best or n == 0:
        return (
            "The run completed but produced no scored candidates. Try widening the "
            "action ranges or increasing the scenario budget."
        )
    best_score = current_best.get("judge_score", {}).get("score")
    metrics = current_best.get("metrics", []) or []
    metric_bits = ", ".join(
        f"{m.get('name')}={round(m.get('value'), 4)}"
        for m in metrics[:3]
        if isinstance(m.get("value"), (int, float))
    )
    direction = (objectives or {}).get("type", "optimize")
    parts = [
        f"Evaluated {n} scenario{'s' if n != 1 else ''} to {direction} the objective."
    ]
    if best_score is not None:
        parts.append(f"The best configuration scored {round(best_score, 4)}.")
    if metric_bits:
        parts.append(f"Top candidate metrics: {metric_bits}.")
    return " ".join(parts)


def _build_narrative(
    objectives: Optional[Dict[str, Any]],
    current_best: Optional[Dict[str, Any]],
    summary: Dict[str, Any],
) -> Dict[str, Any]:
    """Grounded natural-language answer for the run.

    Falls back to a deterministic template if no LLM provider is available. The
    LLM is instructed to use ONLY the supplied numbers, so it explains results
    rather than inventing them.
    """
    template = _template_narrative(objectives, current_best, summary)
    try:
        from services.common import llm
    except Exception:  # pragma: no cover
        return {"text": template, "generated_by": "template"}

    if not llm.is_enabled() or not llm.available_providers() or not current_best:
        return {"text": template, "generated_by": "template"}

    facts = {
        "question": (objectives or {}).get("description", ""),
        "objective_direction": (objectives or {}).get("type", "optimize"),
        "objective_metrics": (objectives or {}).get("metrics", []),
        "scenarios_simulated": summary.get("completed"),
        "best_score": current_best.get("judge_score", {}).get("score"),
        "best_candidate_metrics": current_best.get("metrics", []),
        "mean_score": summary.get("mean_score"),
    }
    system = (
        "You are a decision analyst summarizing a completed simulation study for a "
        "stakeholder. Write 2-4 clear, plain sentences. Use ONLY the numbers in the "
        "provided data; never invent metrics or values. State what was optimized, the "
        "best result found, and any notable trade-off. Do not use markdown headings."
    )
    try:
        resp = llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(facts, default=str)},
            ],
            tier=llm.LLMTier.STANDARD,
            temperature=0.3,
            max_tokens=400,
        )
        text = resp.text.strip()
        if text:
            return {"text": text, "generated_by": resp.provider}
    except llm.LLMError as exc:
        logger.info("Narrative LLM unavailable (%s); using template", type(exc).__name__)
    return {"text": template, "generated_by": "template"}


def _normalize_judge_breakdown(items: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    """Normalize legacy {metric,value,contribution} rows to UI schema."""
    normalized: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if item.get("metric_name") is not None and item.get("raw_value") is not None:
            normalized.append(item)
            continue
        metric = item.get("metric_name") or item.get("metric") or "metric"
        raw = item.get("raw_value", item.get("value", 0.0))
        contrib = item.get("contribution", raw)
        try:
            raw_f = float(raw)
        except (TypeError, ValueError):
            raw_f = 0.0
        try:
            contrib_f = float(contrib)
        except (TypeError, ValueError):
            contrib_f = raw_f
        ts = item.get("threshold_score")
        if ts is None:
            ts = min(1.0, max(0.0, abs(contrib_f) / max(abs(contrib_f), 1.0)))
        weight = item.get("weight", 1.0)
        normalized.append(
            {
                "metric_name": metric,
                "raw_value": raw_f,
                "threshold_score": float(ts),
                "weight": float(weight) if weight is not None else 1.0,
            }
        )
    return normalized


@activity.defn
async def persist_run_progress(
    run_id: str,
    all_scored: List[Dict[str, Any]],
    summary: Dict[str, Any],
    counters_meta: Dict[str, Any] | None = None,
    objectives: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build counters, ranked candidates and current_best into run_spec.

    This is what makes finished runs actually show results in the API/UI. The
    ``confidence`` and ``level`` values are transparent heuristics derived from
    each scenario's rank among candidates (not calibrated uncertainty).
    """
    counters_meta = counters_meta or {}

    # Deduplicate by scenario, keeping the highest score per scenario.
    best_by_id: Dict[str, Dict[str, Any]] = {}
    for row in all_scored:
        if row.get("status") != "scored" or row.get("score") is None:
            continue
        sid = row.get("scenario_id")
        if sid is None:
            continue
        if sid not in best_by_id or row["score"] > best_by_id[sid]["score"]:
            best_by_id[sid] = row

    ranked = sorted(best_by_id.values(), key=lambda r: r["score"], reverse=True)
    scores = [r["score"] for r in ranked]
    s_max = max(scores) if scores else 0.0
    s_min = min(scores) if scores else 0.0
    span = (s_max - s_min) or 1.0
    n = len(ranked)

    def level_for(index: int) -> str:
        if n <= 1:
            return "good"
        frac = index / (n - 1)  # 0.0 = best, 1.0 = worst
        if frac <= 0.2:
            return "excellent"
        if frac <= 0.4:
            return "very_good"
        if frac <= 0.6:
            return "good"
        if frac <= 0.8:
            return "acceptable"
        return "unacceptable"

    candidates: List[Dict[str, Any]] = []
    for index, row in enumerate(ranked[:20]):
        outcome = row.get("outcome", {}) or {}
        metrics = outcome.get("metrics", []) or []
        bench = row.get("benchmark_results", []) or []
        passed = sum(1 for b in bench if b.get("passed") is True)
        confidence = round(0.5 + 0.5 * ((row["score"] - s_min) / span), 3)
        breakdown = _normalize_judge_breakdown(row.get("breakdown", []))
        candidates.append(
            {
                "id": row.get("scenario_id"),
                "run_id": str(run_id),
                "state": row.get("state") or outcome.get("state") or {},
                "actions": row.get("actions") or outcome.get("actions") or {},
                "fidelity": row.get("fidelity") or outcome.get("fidelity") or "cheap",
                "seed": row.get("seed") or 0,
                "metrics": metrics,
                "judge_score": {
                    "scenario_id": row.get("scenario_id"),
                    "score": row.get("score"),
                    "level": level_for(index),
                    "breakdown": breakdown,
                    "benchmarks_passed": passed,
                    "benchmarks_total": len(bench),
                },
                "constraint_violations": [],
                "confidence": confidence,
            }
        )

    current_best = candidates[0] if candidates else None

    # Grounded natural-language answer. The LLM call is blocking, so run it off
    # the event loop; it degrades to a deterministic template if unavailable.
    narrative = await asyncio.to_thread(
        _build_narrative, objectives, current_best, summary
    )

    counters = {
        "scenarios_proposed": int(
            counters_meta.get(
                "scenarios_proposed", summary.get("total_scenarios", len(all_scored))
            )
        ),
        "scenarios_simulated": int(summary.get("completed", n)),
        "scenarios_promoted": int(counters_meta.get("scenarios_promoted", 0)),
        "cache_hits": int(counters_meta.get("cache_hits", 0)),
        "compute_cost": float(counters_meta.get("compute_cost", 0.0)),
        "storage_cost": float(counters_meta.get("storage_cost", 0.0)),
        "budget_consumed": float(counters_meta.get("budget_consumed", n)),
        "budget_total": float(counters_meta.get("budget_total", 0.0)),
    }

    async with get_session() as session:
        run = await session.get(models.Run, _to_uuid(run_id))
        if run is not None:
            spec = dict(run.run_spec or {})
            spec["counters"] = counters
            spec["candidates"] = candidates
            spec["current_best"] = current_best
            spec["summary"] = summary
            spec["narrative"] = narrative
            run.run_spec = spec
            flag_modified(run, "run_spec")
            await session.commit()

    return {
        "candidates": len(candidates),
        "best_score": current_best["judge_score"]["score"] if current_best else None,
        "narrative": narrative.get("text"),
    }


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

    # Build PDF from live run record and store on disk for download.
    pdf_meta: Dict[str, Any] = {"pdf_available": False}
    try:
        from pathlib import Path
        from services.report.pdf_builder import build_run_report_pdf, run_record_to_report_data

        async with get_session() as session:
            run = await session.get(models.Run, _to_uuid(run_id))
            if run is not None:
                spec = dict(run.run_spec or {})
                if report_payload.get("summary") and not spec.get("summary"):
                    spec["summary"] = report_payload["summary"]
                run_data = run_record_to_report_data(run, spec)
                pdf_bytes = build_run_report_pdf(run_data)
                reports_dir = Path(__file__).resolve().parents[3] / "data" / "reports"
                reports_dir.mkdir(parents=True, exist_ok=True)
                pdf_path = reports_dir / f"{run_id}.pdf"
                pdf_path.write_bytes(pdf_bytes)
                pdf_meta = {
                    "pdf_available": True,
                    "pdf_path": str(pdf_path),
                    "pdf_size_bytes": len(pdf_bytes),
                }
                spec["report_pdf"] = pdf_meta
                run.run_spec = spec
                flag_modified(run, "run_spec")
                await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF report generation failed for run %s: %s", run_id, exc)

    artifact = await persist_artifact(
        run_id=run_id,
        object_key=object_key,
        checksum=checksum,
        artifact_type="report",
        content_type="application/json",
        size_bytes=len(encoded),
    )
    return {**artifact, **pdf_meta}
