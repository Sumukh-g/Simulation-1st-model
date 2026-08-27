#!/usr/bin/env python3
"""Publication figures from the Chapter 4 benchmark campaign. No app source edits."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
FIG = HERE / "figures"
FIG.mkdir(parents=True, exist_ok=True)

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Liberation Serif", "DejaVu Serif"],
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "figure.dpi": 200,
        "savefig.dpi": 300,
        "axes.grid": True,
        "grid.alpha": 0.3,
    }
)

BACKEND_COLOUR = {
    "evolutionary": "#1f4e79",
    "bayesian": "#c45911",
    "hybrid": "#548235",
    "random": "#7f7f7f",
}
BACKEND_LABEL = {
    "evolutionary": "Evolutionary",
    "bayesian": "Bayesian",
    "hybrid": "Hybrid",
    "random": "Random search",
}


def load_results():
    bundle = json.loads((EVIDENCE / "benchmark_campaign.json").read_text(encoding="utf-8"))
    return [r for r in bundle["results"] if r.get("status") == "completed"]


def grouped(results):
    table = defaultdict(list)
    for row in results:
        table[(row["problem"], row["backend"])].append(row)
    return table


def _box(ax, data, labels, colours):
    bp = ax.boxplot(data, labels=labels, patch_artist=True, showfliers=True)
    for patch, colour in zip(bp["boxes"], colours):
        patch.set_facecolor(colour)
        patch.set_alpha(0.65)


def figure_hypervolume(results):
    groups = grouped(results)
    problems = ["zdt1", "zdt2", "dtlz2"]
    backends = ["evolutionary", "bayesian", "hybrid", "random"]
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.4), sharey=False)
    for ax, problem in zip(axes, problems):
        data, labels, colours = [], [], []
        for backend in backends:
            rows = groups.get((problem, backend), [])
            values = [r["hypervolume"] for r in rows if r.get("hypervolume") is not None]
            if values:
                data.append(values)
                labels.append(BACKEND_LABEL[backend])
                colours.append(BACKEND_COLOUR[backend])
        if data:
            _box(ax, data, labels, colours)
        ax.set_title(problem.upper())
        ax.set_ylabel("Hypervolume (higher is better)")
        ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    path = FIG / "figure_4_2_hypervolume.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def figure_igd(results):
    groups = grouped(results)
    problems = ["zdt1", "zdt2", "dtlz2"]
    backends = ["evolutionary", "bayesian", "hybrid", "random"]
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.4))
    for ax, problem in zip(axes, problems):
        data, labels, colours = [], [], []
        for backend in backends:
            rows = groups.get((problem, backend), [])
            values = [r["igd"] for r in rows if r.get("igd") is not None and np.isfinite(r["igd"])]
            if values:
                data.append(values)
                labels.append(BACKEND_LABEL[backend])
                colours.append(BACKEND_COLOUR[backend])
        if data:
            _box(ax, data, labels, colours)
        ax.set_title(problem.upper())
        ax.set_ylabel("IGD (lower is better)")
        ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    path = FIG / "figure_4_3_igd.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def figure_convergence(results):
    # Median hypervolume versus evaluations for ZDT1.
    backends = ["evolutionary", "bayesian", "hybrid", "random"]
    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    for backend in backends:
        series = [r for r in results if r["problem"] == "zdt1" and r["backend"] == backend]
        if not series:
            continue
        # Align by evaluation count using the first history record present.
        by_eval = defaultdict(list)
        for row in series:
            for rec in row.get("history") or []:
                by_eval[rec["evaluations"]].append(rec["hypervolume"])
        xs = sorted(by_eval)
        ys = [float(np.median(by_eval[x])) for x in xs]
        ax.plot(xs, ys, color=BACKEND_COLOUR[backend], label=BACKEND_LABEL[backend], linewidth=1.8)
    ax.set_xlabel("Completed objective evaluations")
    ax.set_ylabel("Median hypervolume (ZDT1)")
    ax.legend(frameon=False)
    fig.tight_layout()
    path = FIG / "figure_4_1_convergence_zdt1.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def figure_pareto(results):
    fig, axes = plt.subplots(1, 2, figsize=(8.8, 3.8))
    for ax, problem in zip(axes, ["zdt1", "zdt2"]):
        for backend in ["evolutionary", "bayesian", "hybrid"]:
            rows = [r for r in results if r["problem"] == problem and r["backend"] == backend]
            if not rows:
                continue
            # Representative seed: median hypervolume run.
            rows = sorted(rows, key=lambda r: r.get("hypervolume") or 0.0)
            mid = rows[len(rows) // 2]
            front = np.array(mid.get("front") or [])
            if front.size == 0:
                continue
            ax.scatter(
                front[:, 0],
                front[:, 1],
                s=18,
                alpha=0.75,
                label=f"{BACKEND_LABEL[backend]} seed {mid['seed']}",
                color=BACKEND_COLOUR[backend],
            )
        ax.set_xlabel("f1")
        ax.set_ylabel("f2")
        ax.set_title(f"{problem.upper()} non-dominated front (median-HV seed)")
        ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    path = FIG / "figure_4_4_pareto.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def figure_failures(results):
    # Zero hypervolume rate as a proxy for fronts outside the reference box.
    problems = ["zdt1", "zdt2", "dtlz2"]
    backends = ["evolutionary", "bayesian", "hybrid", "random"]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    x = np.arange(len(problems))
    width = 0.18
    for i, backend in enumerate(backends):
        rates = []
        for problem in problems:
            rows = [r for r in results if r["problem"] == problem and r["backend"] == backend]
            if not rows:
                rates.append(0.0)
                continue
            n_zero = sum(1 for r in rows if (r.get("hypervolume") or 0.0) == 0.0)
            n_fail = sum(1 for r in rows if r.get("status") != "completed")
            rates.append((n_zero + n_fail) / len(rows))
        ax.bar(
            x + (i - 1.5) * width,
            rates,
            width,
            label=BACKEND_LABEL[backend],
            color=BACKEND_COLOUR[backend],
        )
    ax.set_xticks(x)
    ax.set_xticklabels([p.upper() for p in problems])
    ax.set_ylabel("Share of runs with HV = 0")
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, ncol=2)
    fig.tight_layout()
    path = FIG / "figure_4_5_zero_hypervolume.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def main() -> int:
    results = load_results()
    paths = [
        figure_convergence(results),
        figure_hypervolume(results),
        figure_igd(results),
        figure_pareto(results),
        figure_failures(results),
    ]
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
