# Optimiser benchmark findings (Phase 0)

The engine has to be proved on problems whose answers are known analytically,
not on a bundled domain pack. If the optimiser only looked good on a pack we
shipped ourselves, we would have proved nothing about the platform. Everything
below comes from `scripts/run_benchmark.py` against the ZDT family, and every
run is reproducible from its spec plus its seed.

## The run

```
python scripts/run_benchmark.py --spec configs/benchmarks/zdt1_smoke.yaml
```

ZDT1, 5 decision variables, 200 evaluations, batch size 20, seed 42, reference
point (1.1, 1.1). Hypervolume is exact in two objectives; higher is better. IGD
is distance to a 200-point sample of the analytic front; lower is better.

| backend | hypervolume | IGD | front size | wall clock |
|---|---|---|---|---|
| evolutionary | 0.2216 | 0.4563 | 13 | 2.8 s |
| bayesian | 0.5701 | 0.1855 | 6 | 102.8 s |
| hybrid | 0.0000 (empty) | 1.1186 | 19 | 128.1 s |

Both single-strategy backends converge, which is the Phase 0 acceptance
criterion: the engine works. The comparison between them is not meaningful at
this budget — 200 evaluations is a smoke test, not a ranking — but the shape is
the expected one. The GP is far more sample-efficient and far slower per
evaluation; the population search is cheap and covers more of the front.

## The hybrid is worse than either of its halves

That is not sampling noise. `UnifiedOptimizer` in `HYBRID` mode splits each
batch between its Bayesian and evolutionary components, and its Bayesian
component is single-objective: `_init_bayesian` builds one `BayesianOptimizer`
on `config.objectives[0]` and `update()` feeds it only that objective's value.

On any multi-objective problem this means half the evaluation budget is spent
driving objective 0 to its extreme with no pressure whatsoever on the others.
Instrumenting a 200-evaluation ZDT1 run by proposal source:

| source | evaluations | f1 mean | f1 min | f2 mean | f2 min |
|---|---|---|---|---|---|
| bayesian | 99 | 0.4834 | 0.0206 | 4.0549 | 2.1340 |
| evolutionary | 101 | 0.3468 | 0.0108 | 3.8206 | 1.3177 |

ZDT1's front has f2 <= 1 everywhere. Nothing the hybrid found comes close, so
its entire front lies outside the reference box and hypervolume is legitimately
zero. The damage is not confined to the wasted half of the budget: points with
near-zero f1 and terrible f2 are non-dominated, so they occupy the first front
and crowd out the evolutionary half's parent pool. The two strategies share one
archive, which is the whole idea, and that is exactly why one of them optimising
the wrong thing poisons the other.

The standalone `bayesian` backend does not have this problem. It scalarises with
augmented Chebyshev weights redrawn each iteration (ParEGO) and refits the
surrogate from the archive, so it is always searching for the whole front.

## Two smaller defects found on the way

**Unevaluated individuals accumulate.** `EvolutionaryOptimizer.evolve()` appends
`population_size // 2` offspring to `self.population` regardless of how many the
caller asked for. The hybrid asks for 10 and gets 25, so 15 ghosts per iteration
pile up: after 10 iterations the population held 294 entries of which 110 were
evaluated. Selection filters them out, so results are unaffected, but every
`observe()` does a linear scan over the lot.

**Cubic scaling.** `observe()` calls `_update_pareto_frontier()`, which runs a
full O(n^2) non-dominated sort over the entire archive, once per observation.
That makes a run O(n^3) in the number of evaluations and puts canonical-size
budgets (30 variables, 10k+ evaluations) out of reach. The root cause is that
there is no environmental selection step: a real NSGA-II truncates back to the
population size each generation, so its sort is over a fixed 2N, not over an
archive that grows without bound.

## What this decides

The instruction on optimiser backends was to keep the working v1 code as the
default and add pymoo/BoTorch only where evidence shows they earn it. This is
that evidence, and it points at one specific place: multi-objective Bayesian
optimisation.

A scalarising GP reaches the front one weighting at a time. A hypervolume-based
acquisition function (BoTorch's qEHVI/qNEHVI) optimises the front as a whole,
which is what the hybrid's Bayesian half needs to be doing and currently is not.
The `OptimiserBackend` protocol in `services/optimizer/backends.py` is the seam
that makes adding it a new registration rather than a rewrite.

None of this is Phase 0 work, and none of it is fixed here — Phase 0 proves the
engine and builds the measuring instrument. The fixes belong in Phase 3, where
the optimiser is the subject:

1. Make the hybrid's Bayesian component multi-objective. Either scalarise the
   way `BayesianBackend` already does, or replace it with a BoTorch qNEHVI
   backend. The benchmark harness decides which, at equal budget.
2. Add environmental selection to `EvolutionaryOptimizer` so the population is
   truncated to a fixed size each generation. This fixes the cubic scaling and
   the ghost accumulation together, since both come from the unbounded archive.
3. Re-run `configs/benchmarks/zdt_canonical.yaml` at canonical problem sizes,
   which only becomes affordable once (2) is done.
