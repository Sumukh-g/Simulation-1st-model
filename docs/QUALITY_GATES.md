# GSIP Quality Gates

Quality gates are pass/fail checks required before a feature, run type, or
release can be considered complete. Each gate lists objective criteria and
required evidence.

## Reproducibility Gate

**Goal:** deterministic replay of any run.

**Pass criteria:**
- Deterministic replay: identical run spec + seed yields identical scenario
  hashes and metric outputs (bit-for-bit where feasible, tolerance documented
  where floating-point variance exists).
- Hashed configs: run spec, domain pack version, code version, and environment
  config are hashed and stored in the run ledger and artifact metadata.
- Seed policy: seed derivation is documented; every scenario records its seed;
  no non-deterministic RNG is used without explicit opt-in and logging.

**Required evidence:** replay test report, stored hashes, seed registry entries.

## Evidence Gate

**Goal:** all claims trace back to verifiable sources.

**Pass criteria:**
- Every benchmark entry includes a source reference (URL/DOI/file), author,
  date, and access timestamp.
- Every rubric entry includes supporting evidence or an explicit rationale.
- Every report cites an `EvidencePack` with chunk IDs and source metadata.

**Required evidence:** benchmark/rubric manifests with sources, report citation
tables that map claims to EvidencePack chunk IDs.

## Simulation Gate

**Goal:** simulation outputs are sane and constraints are enforced.

**Pass criteria:**
- Domain pack invariants are defined and enforced (state bounds, conservation
  laws, feasibility checks).
- Sanity checks block NaN/Inf, impossible values, and schema violations.
- Constraint evaluation is executed for every scenario and recorded with the
  outcome bundle.

**Required evidence:** invariant specs, sanity check logs, constraint evaluation
records per scenario.

## Optimization Gate

**Goal:** optimization improves outcomes without leaking sensitive data.

**Pass criteria:**
- Optimization must beat the baseline on `ToyPack` using the standard objective
  set and budget.
- Optimization must not leak or overfit on `FinancePack` (no training on test
  data, no leakage across splits, and audit logs confirm isolation).

**Required evidence:** baseline comparison report, leakage audit results, and
repeatable optimization runs.

## Judge Gate

**Goal:** scoring is deterministic, explainable, and context aware.

**Pass criteria:**
- Deterministic scoring: identical inputs yield identical scores and breakdowns.
- Context-based benchmark selection: benchmarks are selected based on run
  metadata (domain, objectives, constraints) and selection rules are logged.
- Score breakdown includes per-metric contributions, penalties, and confidence
  modifiers.

**Required evidence:** scoring determinism tests, benchmark selection logs,
score breakdown artifacts.

## Security Gate

**Goal:** privileged actions are controlled and auditable.

**Pass criteria:**
- RBAC enforced for all admin and policy endpoints (create/update/delete).
- Audit events emitted for every admin edit, including actor, diff, and
  timestamp.

**Required evidence:** RBAC policy definitions, audit log samples, and access
tests for admin-only flows.

## Observability Gate

**Goal:** system behavior is visible and diagnosable.

**Pass criteria:**
- Distributed traces span API → orchestrator → sim fabric → judge/evidence.
- Metrics dashboards cover latency, throughput, errors, and queue depth.

**Required evidence:** trace screenshots/IDs across services, dashboard links,
SLO/SLI definitions.

## UI Gate

**Goal:** users can compare scenarios and understand trade-offs.

**Pass criteria:**
- Scenario compare view with side-by-side metrics and deltas.
- Pareto view for multi-objective outcomes with selectable points.
- Masked heatmaps with legends and user toggles for layer visibility.

**Required evidence:** UI test snapshots or recordings and associated UX notes.
