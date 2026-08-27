"""Generate structured PDF run reports from persisted run data."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fpdf.enums import XPos, YPos


def _safe(text: Any, limit: int = 500) -> str:
    s = str(text or "").replace("\r", "")
    for src, dst in (
        ("\u202f", " "),
        ("\u00a0", " "),
        ("\u2011", "-"),
        ("\u2013", "-"),
        ("\u2014", "-"),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("…", "..."),
    ):
        s = s.replace(src, dst)
    s = s.encode("latin-1", errors="replace").decode("latin-1")
    return s if len(s) <= limit else s[: limit - 1] + "..."


def _fmt_score(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


def _as_bytes(data: bytes | bytearray) -> bytes:
    return bytes(data) if isinstance(data, bytearray) else data


def run_record_to_report_data(run: Any, spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build the dict consumed by build_run_report_pdf from a Run ORM row."""
    return {
        "id": str(run.id),
        "title": spec.get("title"),
        "status": run.status,
        "simulation_mode": spec.get("simulation_mode"),
        "domain_pack": spec.get("domain_pack"),
        "created_at": run.created_at.isoformat() if run.created_at else "",
        "objective_spec": spec.get("objective_spec", {}),
        "narrative": spec.get("narrative"),
        "assistant_message": spec.get("assistant_message"),
        "classification": spec.get("classification"),
        "candidate_methods": spec.get("candidate_methods"),
        "selected_method": spec.get("selected_method"),
        "selected_method_id": spec.get("selected_method_id"),
        "counters": spec.get("counters", {}),
        "summary": spec.get("summary"),
        "candidates": spec.get("candidates", []),
        "current_best": spec.get("current_best"),
        "draft_pack": spec.get("draft_pack") or spec.get("ephemeral_pack_spec"),
        "ai_simulation_spec": spec.get("ai_simulation_spec"),
        "ephemeral_pack_spec": spec.get("ephemeral_pack_spec"),
    }


def _write_line(pdf, height: float, text: str, *, bold: bool = False, size: int = 10) -> None:
    pdf.set_x(pdf.l_margin)
    style = "B" if bold else ""
    pdf.set_font("Helvetica", style, size)
    pdf.multi_cell(pdf.epw, height, _safe(text))


def _write_section(pdf, title: str) -> None:
    pdf.ln(2)
    _write_line(pdf, 8, title, bold=True, size=13)


def _write_bullets(pdf, items: List[str], limit: int = 12) -> None:
    for item in items[:limit]:
        if item:
            _write_line(pdf, 5, f"- {_safe(item, 400)}")


def _solution_paragraph(run_data: Dict[str, Any]) -> str:
    narrative = run_data.get("narrative") or {}
    text = narrative.get("text") if isinstance(narrative, dict) else None
    if text:
        return str(text)

    best = run_data.get("current_best") or {}
    actions = best.get("actions") or {}
    metrics = best.get("metrics") or []
    if not actions and not metrics:
        return "No ranked solution was produced for this run."

    parts = ["Based on scenario search, the best-ranked policy configuration is:"]
    if actions:
        lever_txt = ", ".join(f"{k}={v}" for k, v in actions.items())
        parts.append(f"Recommended levers: {lever_txt}.")
    if metrics:
        metric_txt = ", ".join(
            f"{m.get('name')}={_fmt_score(m.get('value'))}"
            for m in metrics[:6]
            if isinstance(m, dict)
        )
        parts.append(f"Expected outcomes: {metric_txt}.")
    summary = run_data.get("summary") or {}
    if summary.get("best_score") is not None:
        parts.append(f"Judge score: {_fmt_score(summary.get('best_score'))}.")
    return " ".join(parts)


def build_run_report_pdf(run_data: Dict[str, Any]) -> bytes:
    """Build a clean PDF report from a RunResponse-shaped dict."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    obj = run_data.get("objective_spec") or {}
    prompt = _safe(obj.get("description", ""), 800)
    title = _safe(run_data.get("title") or prompt or "Simulation Run", 120)
    mode = _safe(run_data.get("simulation_mode", "domain_pack"))
    status = _safe(run_data.get("status", "unknown"))
    pack = _safe(run_data.get("domain_pack") or "n/a")
    created = _safe(run_data.get("created_at", ""))[:19]

    _write_line(pdf, 10, "GSIP Simulation Report", bold=True, size=18)
    pdf.ln(2)
    _write_line(pdf, 6, f"Run: {title}")
    _write_line(pdf, 6, f"Mode: {mode}  |  Status: {status}")
    _write_line(pdf, 6, f"Pack: {pack}  |  Created: {created}")

    if prompt:
        _write_section(pdf, "Your Question")
        _write_line(pdf, 5, prompt)

    _write_section(pdf, "What This Simulation Did")
    counters = run_data.get("counters") or {}
    summary = run_data.get("summary") or {}
    simulated = counters.get("scenarios_simulated", summary.get("completed", 0))
    _write_line(
        pdf,
        5,
        (
            f"The engine evaluated {simulated} scenarios. Each scenario applies a different "
            "combination of policy levers to a deterministic model, scores the outcomes, "
            "and ranks the best options. The LLM is used only to set up the problem and "
            "write this report — not once per scenario."
        ),
    )

    draft = run_data.get("draft_pack") or run_data.get("ephemeral_pack_spec") or {}
    ai_spec = run_data.get("ai_simulation_spec") or {}
    selected = run_data.get("selected_method") or {}
    if selected.get("name") or run_data.get("selected_method_id"):
        _write_line(
            pdf,
            5,
            f"Selected method: {_safe(selected.get('name') or run_data.get('selected_method_id'))}",
        )

    levers = draft.get("action_schema") or ai_spec.get("levers") or []
    if levers:
        _write_line(pdf, 5, "Policy levers optimized (0-100 scale):")
        for lever in levers[:10]:
            if isinstance(lever, dict):
                name = lever.get("name", "lever")
                desc = lever.get("description", "")
                _write_line(pdf, 5, f"  - {name}: {_safe(desc, 120)}")

    metrics_def = draft.get("metrics") or ai_spec.get("metrics") or []
    if metrics_def:
        _write_line(pdf, 5, "Metrics tracked:")
        for m in metrics_def[:8]:
            if isinstance(m, dict):
                direction = m.get("direction", "optimize")
                _write_line(pdf, 5, f"  - {m.get('name', 'metric')} ({direction})")

    steps = ai_spec.get("calculation_steps") or draft.get("simulate_outline") or []
    if steps:
        _write_line(pdf, 5, "Simulation steps per scenario:")
        _write_bullets(pdf, [str(s) for s in steps])

    objectives = obj.get("objectives") or []
    if objectives:
        _write_line(pdf, 5, "Optimization objectives:")
        for o in objectives[:8]:
            if isinstance(o, dict) and o.get("name"):
                _write_line(pdf, 5, f"  - {o['name']} ({o.get('direction', 'maximize')})")

    _write_section(pdf, "Answer / Recommended Solution")
    _write_line(pdf, 5, _safe(_solution_paragraph(run_data), 2500))

    _write_section(pdf, "Executive Summary")
    narrative = run_data.get("narrative") or {}
    summary_text = narrative.get("text") if isinstance(narrative, dict) else None
    if summary_text:
        _write_line(pdf, 5, _safe(summary_text, 2500))
    elif run_data.get("assistant_message"):
        _write_line(pdf, 5, _safe(run_data.get("assistant_message"), 1500))

    classification = run_data.get("classification") or {}
    if classification:
        _write_section(pdf, "Problem Classification")
        _write_line(pdf, 5, f"Domain: {_safe(classification.get('domain'))}")
        if classification.get("summary"):
            _write_line(pdf, 5, _safe(classification.get("summary"), 800))

    methods = run_data.get("candidate_methods") or []
    if methods:
        _write_section(pdf, "Methods Considered")
        for m in methods[:8]:
            if not isinstance(m, dict):
                continue
            mark = " (selected)" if m.get("recommended") else ""
            _write_line(
                pdf,
                5,
                f"- {_safe(m.get('name', m.get('id')))}{mark}: {_safe(m.get('why_suitable'), 200)}",
            )

    _write_section(pdf, "Results Summary")
    proposed = counters.get("scenarios_proposed", summary.get("total_scenarios", 0))
    _write_line(pdf, 5, f"Scenarios simulated: {simulated} / {proposed}")
    _write_line(pdf, 5, f"Best judge score: {_fmt_score(summary.get('best_score'))}")
    _write_line(pdf, 5, f"Mean judge score: {_fmt_score(summary.get('mean_score'))}")
    if summary.get("failed"):
        _write_line(pdf, 5, f"Failed scenarios: {summary.get('failed')}")
    if counters.get("scenarios_promoted"):
        _write_line(pdf, 5, f"Finalists promoted to higher fidelity: {counters.get('scenarios_promoted')}")

    best = run_data.get("current_best")
    if best:
        _write_section(pdf, "Best Scenario Detail")
        js = best.get("judge_score") or {}
        _write_line(pdf, 5, f"Scenario ID: {_safe(best.get('id'), 40)}")
        _write_line(pdf, 5, f"Judge score: {_fmt_score(js.get('score'))} ({_safe(js.get('level', 'n/a'))})")
        actions = best.get("actions") or {}
        if actions:
            _write_line(pdf, 5, "Optimal lever settings:")
            for k, v in actions.items():
                _write_line(pdf, 5, f"  - {k}: {v}")
        metrics = best.get("metrics") or []
        if metrics:
            _write_line(pdf, 5, "Outcome metrics:")
            for m in metrics[:10]:
                if not isinstance(m, dict):
                    continue
                unit = f" {_safe(m.get('unit'))}" if m.get("unit") else ""
                _write_line(pdf, 5, f"  - {_safe(m.get('name'))}: {_fmt_score(m.get('value'))}{unit}")

    candidates: List[Dict[str, Any]] = list(run_data.get("candidates") or [])[:10]
    if candidates:
        _write_section(pdf, "Top Ranked Alternatives")
        col_rank, col_score = 14, 32
        col_detail = pdf.epw - col_rank - col_score
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_rank, 6, "Rank", border=1)
        pdf.cell(col_score, 6, "Score", border=1)
        pdf.cell(col_detail, 6, "Key levers / metrics", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 9)
        for i, c in enumerate(candidates, 1):
            js = c.get("judge_score") or {}
            score = _fmt_score(js.get("score"))
            actions = c.get("actions") or {}
            metrics = c.get("metrics") or []
            metric_str = ", ".join(
                f"{m.get('name')}={_fmt_score(m.get('value'))}"
                for m in metrics[:3]
                if isinstance(m, dict)
            )
            lever_str = ", ".join(
                f"{k}={round(float(v), 1)}"
                for k, v in list(actions.items())[:3]
                if isinstance(v, (int, float))
            )
            detail = lever_str or metric_str or _safe(c.get("id"), 40)
            pdf.set_x(pdf.l_margin)
            pdf.cell(col_rank, 6, str(i), border=1)
            pdf.cell(col_score, 6, score, border=1)
            pdf.cell(col_detail, 6, _safe(detail, 80), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    limitations = ai_spec.get("limitations") or []
    assumptions = ai_spec.get("assumptions") or []
    if limitations or assumptions:
        _write_section(pdf, "Assumptions and Limitations")
        if assumptions:
            _write_line(pdf, 5, "Assumptions:")
            _write_bullets(pdf, [str(a) for a in assumptions])
        if limitations:
            _write_line(pdf, 5, "Limitations:")
            _write_bullets(pdf, [str(l) for l in limitations])

    _write_section(pdf, "Important Notes")
    if mode in ("no_pack", "create_pack"):
        fidelity = draft.get("fidelity") or "ILLUSTRATIVE"
        _write_line(
            pdf,
            5,
            (
                f"Fidelity: {fidelity}. This report uses an auto-generated reduced-order model. "
                "Treat results as structured exploration, not validated predictions. "
                "Calibrate against real data before operational or policy decisions."
            ),
        )
    else:
        _write_line(
            pdf,
            5,
            "Results depend on the registered domain pack fidelity and evidence base. "
            "Review benchmarks and assumptions before acting on recommendations.",
        )

    pdf.ln(2)
    _write_line(pdf, 5, f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} by GSIP")

    return _as_bytes(pdf.output())
