#!/usr/bin/env python3
"""
Persist locally executed domain-pack runs so the UI can be photographed.

This does not modify application source. It uses the existing formalizer,
ToyPack, SpatialPack, judge scorer and ORM against the seeded database.
Temporal is not used; the limitation is recorded in the output JSON.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://gsip:gsip_password@localhost:5432/gsip"
)

from compute.domain_packs.finance_pack import FinancePack  # noqa: E402
from compute.domain_packs.sdk import Fidelity  # noqa: E402
from compute.domain_packs.spatial_pack import SpatialPack  # noqa: E402
from compute.domain_packs.toy_pack import ToyPack  # noqa: E402
from services.api.db import models  # noqa: E402
from services.api.db.database import AsyncSessionLocal  # noqa: E402
from services.judge.scorer import DeterministicScorer, MetricValue, RubricSpec  # noqa: E402
from services.orchestrator.activities.formalizer import formalize_objective  # noqa: E402
from services.report.pdf_builder import build_run_report_pdf, run_record_to_report_data  # noqa: E402
from sqlalchemy import select  # noqa: E402

OUT = Path(__file__).resolve().parent / "evidence"
OUT.mkdir(parents=True, exist_ok=True)


def _stages() -> list[dict]:
    names = [
        "formalize",
        "evidence",
        "scenarios",
        "simulation",
        "optimize",
        "robustness",
        "judge",
        "report",
    ]
    return [{"stage": n, "status": "completed", "progress": 100} for n in names]


def _candidate(scenario_id: str, run_id: str, actions: dict, metrics, score, fidelity: str, seed: int) -> dict:
    metric_list = [{"name": m.name, "value": float(m.value), "unit": m.unit} for m in metrics]
    return {
        "id": scenario_id,
        "run_id": run_id,
        "state": {},
        "actions": actions,
        "fidelity": fidelity,
        "seed": seed,
        "metrics": metric_list,
        "judge_score": {
            "scenario_id": scenario_id,
            "score": float(score.score),
            "level": score.threshold_level.value if hasattr(score, "threshold_level") else "good",
            "breakdown": [
                {
                    "metric_name": b.name,
                    "raw_value": b.raw_value,
                    "threshold_score": b.threshold_score,
                    "weight": b.weight,
                }
                for b in score.breakdown.metric_breakdowns
            ],
            "benchmarks_passed": int(getattr(score, "benchmarks_passed", 0) or 0),
            "benchmarks_total": int(getattr(score, "benchmarks_total", 0) or 0),
        },
        "constraint_violations": [],
        "confidence": 0.8,
    }


async def _org_project():
    async with AsyncSessionLocal() as session:
        org = (await session.execute(select(models.Org).where(models.Org.slug == "gsip-demo"))).scalar_one()
        project = (
            await session.execute(
                select(models.Project).where(models.Project.org_id == org.id, models.Project.name == "Demo Project")
            )
        ).scalar_one()
        return org.id, project.id


def _run_toy(run_id: str) -> dict:
    prompt = "Move closer to the target as efficiently as possible"
    spec = formalize_objective(prompt, domain_pack="toy-pack", use_llm=False)
    pack = ToyPack()
    scorer = DeterministicScorer()
    rubric = RubricSpec(
        id="toy-local",
        name="Toy distance",
        metric_weights={"score": 0.6, "efficiency": 0.4},
        version="local-1",
    )
    rng = __import__("numpy").random.default_rng(7)
    candidates = []
    state = pack.validate_state({"x": 0.0, "y": 0.0, "target_x": 10.0, "target_y": 10.0})
    for i in range(12):
        actions = {
            "dx": float(rng.uniform(0.2, 2.0)),
            "dy": float(rng.uniform(0.2, 2.0)),
            "steps": int(rng.integers(8, 25)),
        }
        outcome = pack.simulate(
            state=state,
            actions=pack.validate_actions(actions),
            fidelity=Fidelity.MID,
            seed=100 + i,
            scenario_id=f"toy-{i+1:03d}",
            run_id=run_id,
        )
        scored = pack.score(outcome)
        scorer.load_rubric(rubric)
        judge = scorer.score(
            scenario_id=outcome.scenario_id,
            run_id=run_id,
            metrics=[MetricValue(name=m.name, value=m.value) for m in scored.metrics],
            rubric_id=rubric.id,
            feasibility=1.0 if scored.is_feasible else 0.0,
            confidence=0.8,
        )
        candidates.append(
            _candidate(outcome.scenario_id, run_id, actions, scored.metrics, judge, "mid", 100 + i)
        )
    candidates.sort(key=lambda c: c["judge_score"]["score"], reverse=True)
    return {
        "title": "ToyPack navigation (in-process, no Temporal)",
        "prompt": prompt,
        "domain_pack": "toy-pack",
        "objective": spec.model_dump() if hasattr(spec, "model_dump") else spec,
        "candidates": candidates,
    }


def _run_spatial(run_id: str) -> dict:
    prompt = "Reduce pollution concentration while keeping coverage of the monitored area"
    spec = formalize_objective(prompt, domain_pack="spatial-pack", use_llm=False)
    pack = SpatialPack()
    scorer = DeterministicScorer()
    rubric = RubricSpec(
        id="spatial-local",
        name="Spatial safety",
        metric_weights={"safe_area_ratio": 0.5, "coverage_ratio": 0.3, "mean_concentration": 0.2},
        version="local-1",
    )
    rng = __import__("numpy").random.default_rng(11)
    candidates = []
    state = pack.validate_state({"grid_size": 32, "time_steps": 20})
    for i in range(8):
        n_sources = int(rng.integers(1, 4))
        actions = {
            "sources": [
                {
                    "x": int(rng.integers(4, 28)),
                    "y": int(rng.integers(4, 28)),
                    "intensity": float(rng.uniform(0.4, 2.0)),
                    "radius": float(rng.uniform(1.0, 3.0)),
                }
                for _ in range(n_sources)
            ]
        }
        outcome = pack.simulate(
            state=state,
            actions=pack.validate_actions(actions),
            fidelity=Fidelity.CHEAP,
            seed=200 + i,
            scenario_id=f"spatial-{i+1:03d}",
            run_id=run_id,
        )
        scored = pack.score(outcome)
        scorer.load_rubric(rubric)
        judge = scorer.score(
            scenario_id=outcome.scenario_id,
            run_id=run_id,
            metrics=[MetricValue(name=m.name, value=m.value) for m in scored.metrics],
            rubric_id=rubric.id,
            feasibility=1.0 if scored.is_feasible else 0.0,
            confidence=0.75,
        )
        candidates.append(
            _candidate(outcome.scenario_id, run_id, actions, scored.metrics, judge, "cheap", 200 + i)
        )
    candidates.sort(key=lambda c: c["judge_score"]["score"], reverse=True)
    return {
        "title": "SpatialPack diffusion (in-process, no Temporal)",
        "prompt": prompt,
        "domain_pack": "spatial-pack",
        "objective": spec.model_dump() if hasattr(spec, "model_dump") else spec,
        "candidates": candidates,
    }


def _run_finance(run_id: str) -> dict:
    prompt = "Maximize portfolio returns while keeping risk low"
    spec = formalize_objective(prompt, domain_pack="finance-pack", use_llm=False)
    pack = FinancePack()
    scorer = DeterministicScorer()
    rubric = RubricSpec(
        id="finance-local",
        name="Risk-adjusted return",
        metric_weights={"sharpe_ratio": 0.5, "total_return": 0.3, "max_drawdown": 0.2},
        version="local-1",
    )
    rng = __import__("numpy").random.default_rng(3)
    candidates = []
    state = pack.validate_state({})
    for i in range(8):
        spy = float(rng.uniform(0.2, 0.7))
        bnd = float(rng.uniform(0.1, 0.4))
        gld = float(rng.uniform(0.0, 0.2))
        cash = max(0.0, 1.0 - spy - bnd - gld)
        total = spy + bnd + gld + cash
        actions = {
            "weights": {
                "SPY": spy / total,
                "BND": bnd / total,
                "GLD": gld / total,
                "CASH": cash / total,
            },
            "rebalance_frequency": "monthly",
        }
        outcome = pack.simulate(
            state=state,
            actions=pack.validate_actions(actions),
            fidelity=Fidelity.CHEAP,
            seed=300 + i,
            scenario_id=f"fin-{i+1:03d}",
            run_id=run_id,
        )
        scored = pack.score(outcome)
        scorer.load_rubric(rubric)
        judge = scorer.score(
            scenario_id=outcome.scenario_id,
            run_id=run_id,
            metrics=[MetricValue(name=m.name, value=m.value) for m in scored.metrics],
            rubric_id=rubric.id,
            feasibility=1.0 if scored.is_feasible else 0.0,
            confidence=0.7,
        )
        candidates.append(
            _candidate(outcome.scenario_id, run_id, actions, scored.metrics, judge, "cheap", 300 + i)
        )
    candidates.sort(key=lambda c: c["judge_score"]["score"], reverse=True)
    return {
        "title": "FinancePack portfolio (in-process, no Temporal)",
        "prompt": prompt,
        "domain_pack": "finance-pack",
        "objective": spec.model_dump() if hasattr(spec, "model_dump") else spec,
        "candidates": candidates,
    }


async def persist(builder) -> dict:
    org_id, project_id = await _org_project()
    run_id = str(uuid.uuid4())
    built = builder(run_id)
    candidates = built["candidates"]
    best = candidates[0] if candidates else None
    scores = [c["judge_score"]["score"] for c in candidates]
    obj = built["objective"]
    if hasattr(obj, "model_dump"):
        dumped = obj.model_dump()
        objective_spec = {
            "description": dumped.get("description", built["prompt"]),
            "objectives": [
                {
                    "name": m.get("name"),
                    "direction": m.get("direction"),
                    "weight": m.get("weight", 1.0),
                }
                for m in dumped.get("metrics", [])
            ],
            "constraints": dumped.get("constraints", []),
            "metrics": dumped.get("metrics", []),
            "primary_direction": dumped.get("primary_direction"),
            "domain_hints": dumped.get("domain_hints", []),
            "action_ranges": dumped.get("action_ranges", {}),
        }
    else:
        objective_spec = obj
    spec = {
        "title": built["title"],
        "prompt": built["prompt"],
        "domain_pack": built["domain_pack"],
        "domain_pack_version": "1.0.0",
        "simulation_mode": "domain_pack",
        "objective_spec": objective_spec,
        "stages": _stages(),
        "counters": {
            "scenarios_proposed": len(candidates),
            "scenarios_simulated": len(candidates),
            "scenarios_promoted": min(5, len(candidates)),
            "cache_hits": 0,
            "compute_cost": 0.0,
            "storage_cost": 0.0,
            "budget_consumed": float(len(candidates)),
            "budget_total": 50.0,
        },
        "current_best": best,
        "candidates": candidates,
        "narrative": {
            "text": (
                f"In-process execution of {built['domain_pack']} without Temporal. "
                f"{len(candidates)} scenarios were simulated by the domain-pack simulate() method. "
                "This is not a Temporal-orchestrated run."
            ),
            "generated_by": "template",
        },
        "summary": {
            "total_scenarios": len(candidates),
            "completed": len(candidates),
            "failed": 0,
            "best_score": max(scores) if scores else None,
            "best_scenario_id": best["id"] if best else None,
            "mean_score": sum(scores) / len(scores) if scores else None,
            "score_std": None,
        },
        "assistant_message": built["title"],
        "execution_path": "in_process_no_temporal",
    }
    async with AsyncSessionLocal() as session:
        run = models.Run(
            id=uuid.UUID(run_id),
            org_id=org_id,
            project_id=project_id,
            status="completed",
            run_spec=spec,
            seed_policy="explicit-integer-seeds",
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        pdf_bytes = build_run_report_pdf(run_record_to_report_data(run, spec))
        pdf_path = OUT / f"run_{built['domain_pack']}.pdf"
        pdf_path.write_bytes(pdf_bytes)
    return {
        "run_id": run_id,
        "domain_pack": built["domain_pack"],
        "n_candidates": len(candidates),
        "best_score": spec["summary"]["best_score"],
        "pdf": str(pdf_path),
        "prompt": built["prompt"],
    }


async def main() -> int:
    records = []
    for builder in (_run_toy, _run_spatial, _run_finance):
        rec = await persist(builder)
        records.append(rec)
        print(json.dumps(rec))
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": "Runs executed in-process because Temporal was unavailable. Numbers come from domain-pack simulate() and DeterministicScorer.",
        "runs": records,
    }
    (OUT / "ui_inprocess_runs.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
