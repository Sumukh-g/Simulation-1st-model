"""Arbitration engine for MoE outputs."""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from .experts import ExpertContract


class ArbitrationResult(BaseModel):
    """Result of arbitration."""

    assumptions: List[str]
    benchmarks: List[Dict[str, Any]]
    scenario_candidates: List[Dict[str, Any]]
    selected_scenarios: List[Dict[str, Any]]
    score_by_scenario: Dict[str, float]
    agreement_score: float
    disagreement_score: float
    conflicts: List[Dict[str, Any]]
    notes: str


class ArbitrationEngine:
    """Merges structured outputs from multiple experts."""

    def __init__(self, consensus_threshold: float = 0.6):
        self.consensus_threshold = consensus_threshold

    def arbitrate(
        self,
        expert_outputs: List[ExpertContract],
        *,
        k_candidates: int = 5,
        simulation_results: List[Dict[str, Any]] | None = None,
    ) -> ArbitrationResult:
        assumptions, assumption_conflicts = self._merge_assumptions(expert_outputs)
        benchmarks, benchmark_conflicts = self._merge_benchmarks(expert_outputs)
        scenarios, score_by_scenario = self._merge_scenarios(expert_outputs)

        selected = self._select_scenarios(
            scenarios,
            score_by_scenario,
            simulation_results or [],
            k_candidates,
        )

        conflicts = assumption_conflicts + benchmark_conflicts
        disagreement = self._compute_disagreement(assumptions, benchmarks, conflicts)
        agreement = 1.0 - disagreement

        return ArbitrationResult(
            assumptions=assumptions,
            benchmarks=benchmarks,
            scenario_candidates=scenarios,
            selected_scenarios=selected,
            score_by_scenario=score_by_scenario,
            agreement_score=agreement,
            disagreement_score=disagreement,
            conflicts=conflicts,
            notes="Consensus merge + scenario union with scoring",
        )

    def _merge_assumptions(
        self, expert_outputs: List[ExpertContract]
    ) -> tuple[List[str], List[Dict[str, Any]]]:
        counts: Dict[str, int] = {}
        for output in expert_outputs:
            for assumption in output.assumptions:
                counts[assumption] = counts.get(assumption, 0) + 1

        required = max(1, int(len(expert_outputs) * self.consensus_threshold + 0.5))
        consensus = [a for a, c in counts.items() if c >= required]
        conflicts = [
            {"type": "assumption", "value": a, "count": c}
            for a, c in counts.items()
            if c < required
        ]
        return consensus, conflicts

    def _merge_benchmarks(
        self, expert_outputs: List[ExpertContract]
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        counts: Dict[str, int] = {}
        items: Dict[str, Dict[str, Any]] = {}
        for output in expert_outputs:
            candidates = output.payload.get("benchmark_candidates", [])
            for candidate in candidates:
                key = f"{candidate.get('name')}::{candidate.get('metric')}"
                counts[key] = counts.get(key, 0) + 1
                items[key] = candidate

        required = max(1, int(len(expert_outputs) * self.consensus_threshold + 0.5))
        consensus = [items[k] for k, c in counts.items() if c >= required]
        conflicts = [
            {"type": "benchmark", "value": items[k], "count": c}
            for k, c in counts.items()
            if c < required
        ]
        return consensus, conflicts

    def _merge_scenarios(
        self, expert_outputs: List[ExpertContract]
    ) -> tuple[List[Dict[str, Any]], Dict[str, float]]:
        merged: Dict[str, Dict[str, Any]] = {}
        scores: Dict[str, float] = {}
        weights: Dict[str, float] = {}

        for output in expert_outputs:
            confidence = output.confidence
            ideas = output.payload.get("scenario_ideas", [])
            for idea in ideas:
                scenario_id = idea.get("scenario_id") or self._scenario_id(idea)
                merged.setdefault(scenario_id, {**idea, "scenario_id": scenario_id})
                priority = float(idea.get("priority", 0.5))
                scores[scenario_id] = scores.get(scenario_id, 0.0) + priority * confidence
                weights[scenario_id] = weights.get(scenario_id, 0.0) + confidence

        scored = {}
        for scenario_id, total in scores.items():
            weight = weights.get(scenario_id, 1.0)
            scored[scenario_id] = total / weight if weight else 0.0

        scenarios = list(merged.values())
        scenarios.sort(key=lambda s: scored.get(s["scenario_id"], 0.0), reverse=True)
        return scenarios, scored

    def _select_scenarios(
        self,
        scenarios: List[Dict[str, Any]],
        scores: Dict[str, float],
        simulation_results: List[Dict[str, Any]],
        k_candidates: int,
    ) -> List[Dict[str, Any]]:
        if simulation_results:
            return self._tournament_select(simulation_results, scenarios, k_candidates)
        return scenarios[:k_candidates]

    def _tournament_select(
        self,
        simulation_results: List[Dict[str, Any]],
        scenarios: List[Dict[str, Any]],
        k_candidates: int,
    ) -> List[Dict[str, Any]]:
        scores = {item["scenario_id"]: item["score"] for item in simulation_results}
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        winners: List[str] = []

        left = 0
        right = len(ranked) - 1
        while left <= right and len(winners) < k_candidates:
            high_id, _ = ranked[left]
            low_id, _ = ranked[right]
            winner = high_id if scores.get(high_id, 0.0) >= scores.get(low_id, 0.0) else low_id
            winners.append(winner)
            left += 1
            right -= 1

        scenario_map = {item["scenario_id"]: item for item in scenarios}
        return [scenario_map[sid] for sid in winners if sid in scenario_map]

    def _scenario_id(self, idea: Dict[str, Any]) -> str:
        digest = hashlib.sha1(str(idea).encode("utf-8")).hexdigest()  # noqa: S324
        return f"scenario-{digest[:12]}"

    def _compute_disagreement(
        self,
        assumptions: List[str],
        benchmarks: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
    ) -> float:
        total_items = len(assumptions) + len(benchmarks) + len(conflicts)
        if total_items == 0:
            return 0.0
        return len(conflicts) / total_items

    def compute_top_gap(self, simulation_results: List[Dict[str, Any]]) -> float | None:
        if len(simulation_results) < 2:
            return None
        ranked = sorted(simulation_results, key=lambda item: item["score"], reverse=True)
        return float(ranked[0]["score"]) - float(ranked[1]["score"])


# Backwards-compatible alias
Arbitrator = ArbitrationEngine
