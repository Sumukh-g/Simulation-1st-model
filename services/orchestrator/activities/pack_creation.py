"""Bootstrap on-demand pack creation and no-pack AI specs via LLM.

These helpers run at run-start for ``create_pack`` / ``no_pack`` so each prompt
gets a *prompt-specific* classification, method catalog, and draft pack — not a
canned “still being wired” string.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from services.common import llm

logger = logging.getLogger(__name__)

_CREATE_SYSTEM = """You are GSIP's domain-pack architect.
Given a user optimization/simulation problem, return JSON with:
{
  "domain": short domain label (e.g. "urban_environment/air_quality"),
  "problem_type": one-line problem class,
  "summary": 2-3 sentences explaining the problem in your own words (must reference specifics from the user prompt),
  "objectives": [{"name": str, "direction": "minimize"|"maximize", "rationale": str}],
  "constraints": [{"name": str, "type": "hard"|"soft", "note": str}],
  "candidate_methods": [
    {"id": str, "name": str, "why_suitable": str, "data_needs": [str], "recommended": bool}
  ],
  "recommended_method_id": str,
  "draft_pack": {
    "name": kebab-case pack id suggestion,
    "display_name": str,
    "fidelity": "TOY"|"UNVALIDATED"|"REDUCED_ORDER",
    "state_schema": [{"name": str, "type": "number"|"string"|"bool", "unit": str|null, "description": str}],
    "action_schema": [{"name": str, "type": "number"|"string"|"bool", "unit": str|null, "description": str}],
    "metrics": [{"name": str, "direction": "minimize"|"maximize", "unit": str|null}],
    "simulate_outline": 3-6 bullet steps describing what simulate() would compute (no fabricated numeric results)
  },
  "assistant_message": markdown string for the user: classify the problem, list methods with a recommendation, summarize the draft pack, and ask them to confirm a method. Must be specific to THIS prompt — never a generic stub.
}
Provide 3-5 distinct candidate_methods. Do not invent simulation result numbers."""

_NO_PACK_SYSTEM = """You are GSIP's AI-defined simulation designer.
The user chose to proceed WITHOUT a registered domain pack. Draft an ephemeral
pack-like simulation spec for this run only. Return JSON with:
{
  "domain": short domain label,
  "summary": 2-3 sentences specific to the user prompt,
  "objectives": [{"name": str, "direction": "minimize"|"maximize", "rationale": str}],
  "ai_simulation_spec": {
    "approach": str,
    "state_variables": [{"name": str, "description": str}],
    "levers": [{"name": str, "description": str}],
    "metrics": [{"name": str, "direction": "minimize"|"maximize"}],
    "calculation_steps": [str],
    "assumptions": [str],
    "limitations": [str]
  },
  "ephemeral_pack": {
    "name": kebab-case id,
    "display_name": str,
    "fidelity": "ILLUSTRATIVE",
    "state_schema": [{"name": str, "type": "number"|"string"|"bool", "description": str}],
    "action_schema": [{"name": str, "type": "number"|"string"|"bool", "description": str}],
    "metrics": [{"name": str, "direction": "minimize"|"maximize"}]
  },
  "assistant_message": markdown for the user explaining the proposed ephemeral pack/simulation for THIS prompt, caveats (illustrative), and that they can switch to Create domain pack for a reusable ratified pack. No fabricated result numbers.
}"""


def _snippet(prompt: str, n: int = 60) -> str:
    p = " ".join(prompt.split())
    return p if len(p) <= n else p[: n - 1] + "…"


def _heuristic_create(prompt: str) -> Dict[str, Any]:
    """Prompt-specific fallback when LLMs are unavailable."""
    lower = prompt.lower()
    if any(w in lower for w in ("pollution", "air", "emission", "delhi", "smog", "aqi")):
        domain = "urban_environment/air_quality"
        methods = [
            {
                "id": "dispersion_intervention",
                "name": "Intervention + dispersion proxy",
                "why_suitable": "Models emission levers and concentration outcomes for city air quality.",
                "data_needs": ["baseline emissions", "meteorology proxy", "population exposure"],
                "recommended": True,
            },
            {
                "id": "multi_sector_abatement",
                "name": "Multi-sector abatement cost curves",
                "why_suitable": "Compares transport/industry/household levers under a pollution-reduction target.",
                "data_needs": ["sector baselines", "cost curves"],
                "recommended": False,
            },
            {
                "id": "policy_scenario_mc",
                "name": "Policy scenario Monte Carlo",
                "why_suitable": "Stress-tests uncertain adoption and meteorology.",
                "data_needs": ["policy packages", "uncertainty ranges"],
                "recommended": False,
            },
        ]
        metrics = [
            {"name": "pollution_index", "direction": "minimize", "unit": "index"},
            {"name": "cost", "direction": "minimize", "unit": "currency"},
        ]
        actions = [
            {"name": "transit_shift_pct", "type": "number", "unit": "%", "description": "Mode shift to public transit"},
            {"name": "industrial_scrubber_coverage", "type": "number", "unit": "%", "description": "Industry abatement coverage"},
            {"name": "ev_adoption_pct", "type": "number", "unit": "%", "description": "EV fleet share increase"},
        ]
    elif any(w in lower for w in ("stock", "portfolio", "return", "finance", "invest", "risk", "sharpe")):
        domain = "finance/portfolio"
        methods = [
            {
                "id": "mean_variance",
                "name": "Mean-variance optimization",
                "why_suitable": "Classic risk/return trade-off for portfolios.",
                "data_needs": ["returns", "covariance"],
                "recommended": True,
            },
            {
                "id": "monte_carlo_wealth",
                "name": "Monte Carlo wealth paths",
                "why_suitable": "Forward-looking distributions under uncertain markets.",
                "data_needs": ["return assumptions", "horizon"],
                "recommended": False,
            },
            {
                "id": "dcf_valuation",
                "name": "Discounted cash flow",
                "why_suitable": "When the question is asset/company valuation.",
                "data_needs": ["cash flows", "discount rate"],
                "recommended": False,
            },
        ]
        metrics = [
            {"name": "sharpe_ratio", "direction": "maximize", "unit": None},
            {"name": "max_drawdown", "direction": "minimize", "unit": "fraction"},
        ]
        actions = [
            {"name": "equity_weight", "type": "number", "unit": "fraction", "description": "Equity allocation"},
            {"name": "bond_weight", "type": "number", "unit": "fraction", "description": "Bond allocation"},
        ]
    else:
        domain = "general/optimization"
        methods = [
            {
                "id": "scenario_search",
                "name": "Scenario search + scoring",
                "why_suitable": f"Explores levers for: {_snippet(prompt)}",
                "data_needs": ["state baselines", "action bounds"],
                "recommended": True,
            },
            {
                "id": "system_dynamics",
                "name": "Reduced-order system dynamics",
                "why_suitable": "Captures feedback when stocks/flows matter.",
                "data_needs": ["stocks", "flows", "time horizon"],
                "recommended": False,
            },
            {
                "id": "constraint_solver",
                "name": "Constrained numerical optimization",
                "why_suitable": "When hard constraints dominate.",
                "data_needs": ["objective", "constraints"],
                "recommended": False,
            },
        ]
        metrics = [
            {"name": "objective_score", "direction": "maximize", "unit": None},
            {"name": "constraint_penalty", "direction": "minimize", "unit": None},
        ]
        actions = [
            {"name": "lever_a", "type": "number", "unit": None, "description": "Primary controllable lever"},
            {"name": "lever_b", "type": "number", "unit": None, "description": "Secondary lever"},
        ]

    pack_name = re.sub(r"[^a-z0-9]+", "-", domain.split("/")[-1].lower()).strip("-") + "-draft"
    recommended = next((m for m in methods if m.get("recommended")), methods[0])
    method_lines = "\n".join(
        f"- **{m['name']}** (`{m['id']}`): {m['why_suitable']}"
        + (" ← recommended" if m.get("recommended") else "")
        for m in methods
    )
    assistant = (
        f"### Classification\n"
        f"Interpreted your request as **{domain}**: {_snippet(prompt, 120)}\n\n"
        f"### Candidate methods\n{method_lines}\n\n"
        f"### Draft pack (`{pack_name}`, fidelity TOY/UNVALIDATED)\n"
        f"Suggested method: **{recommended['name']}**. "
        f"State/action schemas and metrics are drafted below in the run record. "
        f"Confirm a method to continue pack generation (full simulate() wiring is the next step).\n\n"
        f"_LLM providers were unavailable — used a deterministic heuristic tailored to your prompt._"
    )
    return {
        "domain": domain,
        "problem_type": domain,
        "summary": f"User asked: {prompt.strip()}",
        "objectives": [{"name": m["name"], "direction": m["direction"], "rationale": "Derived from prompt"} for m in metrics],
        "constraints": [],
        "candidate_methods": methods,
        "recommended_method_id": recommended["id"],
        "draft_pack": {
            "name": pack_name,
            "display_name": pack_name.replace("-", " ").title(),
            "fidelity": "TOY",
            "state_schema": [
                {"name": "baseline", "type": "number", "unit": None, "description": "Baseline level for the primary metric"}
            ],
            "action_schema": actions,
            "metrics": metrics,
            "simulate_outline": [
                "Read baseline state",
                "Apply selected action levers",
                "Compute metrics for this scenario",
                "Return metric dict (no LLM-invented scores)",
            ],
        },
        "assistant_message": assistant,
        "generated_by": "heuristic",
    }


def _heuristic_no_pack(prompt: str) -> Dict[str, Any]:
    created = _heuristic_create(prompt)
    draft = created["draft_pack"]
    assistant = (
        f"### No registered pack — ephemeral draft for this run\n"
        f"For: _{_snippet(prompt, 140)}_\n\n"
        f"Proposed illustrative pack **{draft['display_name']}** (`{draft['name']}`) in domain "
        f"**{created['domain']}**.\n\n"
        f"**Approach:** scenario search over the drafted levers, scoring "
        f"{', '.join(m['name'] for m in draft['metrics'])}.\n\n"
        f"**Caveat:** results would be ILLUSTRATIVE until a method is ratified. "
        f"Prefer **Create domain pack** if you want a reusable, reviewable pack.\n\n"
        f"_Heuristic draft (LLM unavailable) — still specific to your prompt._"
    )
    return {
        "domain": created["domain"],
        "summary": created["summary"],
        "objectives": created["objectives"],
        "ai_simulation_spec": {
            "approach": "Ephemeral scenario scoring from drafted schemas",
            "state_variables": [{"name": s["name"], "description": s.get("description", "")} for s in draft["state_schema"]],
            "levers": [{"name": a["name"], "description": a.get("description", "")} for a in draft["action_schema"]],
            "metrics": draft["metrics"],
            "calculation_steps": draft["simulate_outline"],
            "assumptions": ["Reduced-order / illustrative fidelity"],
            "limitations": ["Not a ratified domain pack", "Do not treat as predictive without validation"],
        },
        "ephemeral_pack": {
            "name": draft["name"],
            "display_name": draft["display_name"],
            "fidelity": "ILLUSTRATIVE",
            "state_schema": draft["state_schema"],
            "action_schema": draft["action_schema"],
            "metrics": draft["metrics"],
        },
        "assistant_message": assistant,
        "generated_by": "heuristic",
    }


def _synthesize_create_message(data: Dict[str, Any], prompt: str) -> str:
    methods = data.get("candidate_methods") or []
    lines = [
        f"### Classification\n**{data.get('domain', 'unknown')}** — {data.get('summary') or _snippet(prompt, 140)}",
        "",
        "### Candidate methods",
    ]
    for m in methods:
        if not isinstance(m, dict):
            continue
        mark = " ← recommended" if m.get("recommended") or m.get("id") == data.get("recommended_method_id") else ""
        lines.append(f"- **{m.get('name', m.get('id'))}**{mark}: {m.get('why_suitable', '')}")
    draft = data.get("draft_pack") or {}
    if draft:
        lines.extend(
            [
                "",
                f"### Draft pack (`{draft.get('name', 'draft')}`, fidelity {draft.get('fidelity', 'TOY')})",
                draft.get("simulate_outline")
                and ("Outline: " + "; ".join(draft["simulate_outline"][:4]) if isinstance(draft.get("simulate_outline"), list) else "")
                or f"Suggested method id: {data.get('recommended_method_id', 'n/a')}. Confirm a method to continue.",
            ]
        )
    lines.append("\nConfirm which method to use so we can finalize the pack schemas.")
    return "\n".join(line for line in lines if line is not None)


def bootstrap_create_pack(prompt: str) -> Dict[str, Any]:
    """Classify problem, list methods, draft a pack suggestion."""
    try:
        data = llm.complete_json(
            system=_CREATE_SYSTEM,
            user=f"User problem:\n{prompt.strip()}",
            tier=llm.LLMTier.STANDARD,
            temperature=0.35,
            max_tokens=2048,
        )
        # Ensure methods exist
        if not data.get("candidate_methods"):
            fallback = _heuristic_create(prompt)
            data["candidate_methods"] = fallback["candidate_methods"]
            data["draft_pack"] = data.get("draft_pack") or fallback["draft_pack"]
            data.setdefault("recommended_method_id", fallback["recommended_method_id"])
            data.setdefault("domain", fallback["domain"])
        msg = (data.get("assistant_message") or "").strip()
        if len(msg) < 80:
            data["assistant_message"] = _synthesize_create_message(data, prompt)
        data["generated_by"] = data.get("generated_by") or "llm"
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("create_pack LLM bootstrap failed (%s); using heuristic", type(exc).__name__)
        return _heuristic_create(prompt)


def bootstrap_no_pack(prompt: str) -> Dict[str, Any]:
    """Draft an ephemeral pack / AI simulation spec for no_pack mode."""
    try:
        data = llm.complete_json(
            system=_NO_PACK_SYSTEM,
            user=f"User problem:\n{prompt.strip()}",
            tier=llm.LLMTier.STANDARD,
            temperature=0.35,
            max_tokens=2048,
        )
        if not data.get("assistant_message"):
            data["assistant_message"] = (
                f"Drafted an illustrative simulation for: {_snippet(prompt)}. "
                "See ephemeral_pack in the run record."
            )
        data["generated_by"] = data.get("generated_by") or "llm"
        if not data.get("ephemeral_pack"):
            fallback = _heuristic_no_pack(prompt)
            data["ephemeral_pack"] = fallback["ephemeral_pack"]
            data["ai_simulation_spec"] = data.get("ai_simulation_spec") or fallback["ai_simulation_spec"]
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("no_pack LLM bootstrap failed (%s); using heuristic", type(exc).__name__)
        return _heuristic_no_pack(prompt)


def format_stages_after_create(bootstrap: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"stage": "classify", "status": "completed", "message": bootstrap.get("domain", "")},
        {
            "stage": "candidate_methods",
            "status": "completed",
            "message": f"{len(bootstrap.get('candidate_methods') or [])} methods",
        },
        {
            "stage": "awaiting_method_selection",
            "status": "running",
            "message": f"recommended={bootstrap.get('recommended_method_id', '')}",
        },
    ]


def format_stages_after_no_pack(bootstrap: Dict[str, Any]) -> List[Dict[str, str]]:
    pack = bootstrap.get("ephemeral_pack") or {}
    return [
        {
            "stage": "ai_defined_simulation",
            "status": "completed",
            "message": f"ephemeral draft: {pack.get('name', 'n/a')}",
        },
        {
            "stage": "awaiting_confirmation",
            "status": "running",
            "message": "Confirm to run illustrative simulation (execution landing next)",
        },
    ]


def _standard_pipeline_stages() -> List[Dict[str, str]]:
    return [
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


def _sanitize_pack_name(raw: str) -> str:
    name = re.sub(r"[^a-z0-9]+", "-", (raw or "ephemeral").lower()).strip("-")
    if not name:
        name = "ephemeral-pack"
    if not name.startswith("ephemeral-"):
        name = f"ephemeral-{name[:48]}"
    return name


def _default_action_schema() -> List[Dict[str, Any]]:
    return [
        {"name": "intervention_intensity", "type": "number", "description": "Overall intervention strength (0-100)"},
        {"name": "policy_coverage", "type": "number", "description": "Share of target covered (0-100)"},
        {"name": "budget_fraction", "type": "number", "description": "Budget deployed (0-100)"},
    ]


def _default_metrics_from_objectives(objectives: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    metrics = []
    for o in objectives or []:
        if isinstance(o, dict) and o.get("name"):
            metrics.append(
                {
                    "name": o["name"],
                    "direction": o.get("direction", "maximize"),
                    "unit": o.get("unit"),
                }
            )
    if not metrics:
        metrics = [
            {"name": "primary_outcome", "direction": "maximize", "unit": None},
            {"name": "cost", "direction": "minimize", "unit": "currency"},
        ]
    return metrics


def materialize_for_execution(
    *,
    bootstrap: Dict[str, Any],
    mode: str,
    prompt: str,
) -> Dict[str, Any]:
    """Turn LLM bootstrap into run_spec fields that drive the full Temporal pipeline."""
    draft = dict(bootstrap.get("draft_pack") or bootstrap.get("ephemeral_pack") or {})
    objectives = list(bootstrap.get("objectives") or [])

    if mode == "create_pack":
        methods = bootstrap.get("candidate_methods") or []
        selected = bootstrap.get("recommended_method_id")
        if not selected and methods:
            rec = next((m for m in methods if isinstance(m, dict) and m.get("recommended")), methods[0])
            selected = rec.get("id") if isinstance(rec, dict) else None
        selected_method = next(
            (m for m in methods if isinstance(m, dict) and m.get("id") == selected),
            methods[0] if methods else None,
        )
    else:
        selected = None
        selected_method = None

    if not draft.get("action_schema"):
        draft["action_schema"] = _default_action_schema()
    if not draft.get("metrics"):
        draft["metrics"] = _default_metrics_from_objectives(objectives)
    if not draft.get("state_schema"):
        draft["state_schema"] = [
            {"name": "baseline", "type": "number", "description": "Starting level for primary metric"},
        ]
    if not draft.get("name"):
        domain = str(bootstrap.get("domain") or "custom")
        draft["name"] = _sanitize_pack_name(domain.split("/")[-1])

    pack_name = _sanitize_pack_name(str(draft.get("name")))
    draft["name"] = pack_name
    draft.setdefault("fidelity", "ILLUSTRATIVE" if mode == "no_pack" else "TOY")
    draft.setdefault("display_name", pack_name.replace("-", " ").title())

    # Executable ranges / state for scenario generator
    action_ranges = {f["name"]: {"min": 0.0, "max": 100.0} for f in draft["action_schema"] if f.get("name")}
    initial_state: Dict[str, Any] = {"baseline": 100.0}
    for m in draft["metrics"]:
        mname = m.get("name")
        if not mname:
            continue
        if m.get("direction") == "minimize":
            initial_state[f"{mname}_baseline"] = 100.0
        else:
            initial_state[f"{mname}_baseline"] = 1.0

    prelude = [
        {"stage": "classify", "status": "completed", "message": bootstrap.get("domain", "")},
    ]
    if mode == "create_pack":
        prelude.append(
            {
                "stage": "candidate_methods",
                "status": "completed",
                "message": f"selected={selected}",
            }
        )
        method_name = selected_method.get("name") if isinstance(selected_method, dict) else selected
        prelude.append(
            {
                "stage": "pack_draft",
                "status": "completed",
                "message": f"method={method_name or 'default'}",
            }
        )
    else:
        prelude.append(
            {
                "stage": "ai_defined_simulation",
                "status": "completed",
                "message": f"draft={pack_name}",
            }
        )

    exec_note = (
        "_Illustrative results from a reduced-order ephemeral simulator — not a ratified domain pack._"
        if mode == "no_pack"
        else "_Results from an auto-generated TOY/UNVALIDATED pack draft — confirm before production use._"
    )
    assistant = (bootstrap.get("assistant_message") or "").strip()
    if exec_note not in assistant:
        assistant = f"{assistant}\n\n{exec_note}\n\n**Simulation started** using pack `{pack_name}`."

    return {
        "domain_pack": pack_name,
        "domain_pack_version": "0.1.0-illustrative",
        "domain_pack_id": pack_name,
        "ephemeral": True,
        "ephemeral_pack_spec": draft,
        "draft_pack": draft,
        "ephemeral_pack": draft if mode == "no_pack" else bootstrap.get("ephemeral_pack"),
        "selected_method_id": selected,
        "selected_method": selected_method,
        "action_ranges": action_ranges,
        "initial_state": initial_state,
        "scenario_budget": min(50, 100),
        "budget": min(50, 100),
        "stages": prelude + _standard_pipeline_stages(),
        "mode_status": "running_simulation",
        "assistant_message": assistant,
        "illustrative": mode == "no_pack",
    }

