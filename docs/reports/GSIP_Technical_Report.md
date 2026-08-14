# GSIP Technical Report
## General Simulation Intelligence Platform — System Architecture, Implementation, and Operations

**Document version:** 1.0  
**Classification:** Technical  
**Last updated:** February 2025

---

## Executive Summary

This technical report describes the General Simulation Intelligence Platform (GSIP), an end-to-end decision-laboratory system that converts natural-language goals into formal optimization objectives, generates structured scenario spaces, runs simulations at multiple fidelities via pluggable domain packs, optimizes using Bayesian and evolutionary methods, applies deterministic scoring (Judge), and produces defensible outputs with full audit trails. The report covers system architecture, data flows, component contracts, implementation details, quality gates, security and observability, and operational considerations.

**Key technical principle:** The Non-Negotiable Truth Architecture ensures that all numerical results are produced exclusively by simulation code (domain packs), persisted immediately to the run ledger, and never fabricated by LLMs or other AI components.

---

## 1. Introduction and Problem Statement

### 1.1 Context

Decision-making in complex domains (finance, policy, operations) typically requires:

- Formal definition of objectives and constraints  
- Generation of many candidate scenarios  
- Execution of simulations or backtests  
- Scoring and ranking of outcomes  
- Iterative optimization and reporting  

Traditional tooling forces users to manually define objective functions, parameter ranges, and run logic. General-purpose AI assistants can accept natural language but often produce plausible-looking numerical results without running any simulation, which is unacceptable in regulated or high-stakes contexts.

### 1.2 GSIP Approach

GSIP bridges the gap by:

1. **Understanding intent** — Parsing natural language to extract optimization objectives, constraints, and relevant metrics (formalization).  
2. **Generating scenarios** — Creating diverse parameter combinations (grid, Latin hypercube, random, boundary) with deterministic hashing.  
3. **Running real simulations** — Executing only pluggable domain-pack code (no LLM-generated numbers).  
4. **Scoring deterministically** — Ranking via versioned rubrics and benchmarks (Judge service).  
5. **Optimizing iteratively** — Bayesian/evolutionary optimization with multi-fidelity allocation.  
6. **Maintaining full audit trail** — Run ledger (PostgreSQL), scenario hashes, seeds, artifact checksums.

### 1.3 Non-Negotiable Truth Architecture

**Rule:** LLMs and AI agents may propose objectives, scenarios, and explanations; they must **never** fabricate simulation results.

**Enforcement:**

- Only domain pack `simulate()` methods produce numerical outcomes.  
- Results are persisted to the database before being returned to the workflow.  
- Every scenario has a deterministic hash; identical inputs yield identical outputs.  
- Run ledger stores complete computation provenance (run spec hash, domain pack version, seeds, artifact checksums).

---

## 2. System Architecture

### 2.1 High-Level Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Frontend Layer                                 │
│  ┌─────────────────────────┐  ┌─────────────────────────────────────┐   │
│  │   Next.js Web App       │  │      Next.js Admin Dashboard        │   │
│  │   (port 3000)           │  │      (port 3001)                    │   │
│  └─────────────────────────┘  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           API Gateway                                    │
│                      FastAPI (port 8000)                                │
│                   JWT Auth | RBAC | Metrics                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
┌──────────────────────┐ ┌──────────────────┐ ┌──────────────────────────┐
│   Orchestrator       │ │   Judge Service  │ │   Evidence Service       │
│   (Temporal)         │ │   (port 8001)    │ │   (port 8002)            │
│   Workflows/         │ │   Scoring,       │ │   Ingestion,             │
│   Activities         │ │   Benchmarks,    │ │   Embeddings,             │
│                      │ │   Rubrics        │ │   Search                 │
└──────────────────────┘ └──────────────────┘ └──────────────────────────┘
          │                                              │
          ▼                                              ▼
┌──────────────────────┐                    ┌──────────────────────────┐
│   Sim Fabric (Ray)    │                    │   Milvus Vector DB       │
│   Worker Pools,       │                    │   (port 19530)           │
│   Domain Packs,       │                    │   Embeddings,            │
│   Distributed Exec   │                    │   Similarity Search       │
└──────────────────────┘                    └──────────────────────────┘
          │
          ▼
┌──────────────────────┐
│   Optimizer          │
│   Bayesian,          │
│   Evolutionary,      │
│   Multi-fidelity     │
└──────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│   PostgreSQL | MinIO | Redis | Temporal                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Summary

| Component | Technology | Responsibility |
|-----------|------------|-----------------|
| Web App | Next.js | Chat UI, workspace tabs, SSE consumption, run cards |
| Admin | Next.js | Admin dashboard (port 3001) |
| API Gateway | FastAPI | Auth (JWT), RBAC, run CRUD, SSE streaming, routing |
| Orchestrator | Temporal | Durable workflow (SimulationRunWorkflow), activities |
| Sim Fabric | Ray | Distributed simulation execution, domain pack loading |
| Judge | FastAPI | Deterministic scoring, rubrics, benchmarks |
| Evidence | FastAPI | Document ingestion, chunking, embeddings, Milvus search |
| Optimizer | Python | Bayesian (GP + EI), NSGA-II, Thompson sampling |

---

## 3. End-to-End Data Flow

### 3.1 Run Execution Flow

1. **User** submits a question in the chat (e.g. "Maximize portfolio returns while keeping risk low").  
2. **Web app** sends `POST /api/runs/start` with `prompt`, `domain_pack`, `config` (e.g. `maxScenarios`, `maxWallTime`).  
3. **API** validates project and domain pack, creates `Run` in PostgreSQL, builds `run_spec`, starts Temporal `SimulationRunWorkflow.run(run_spec)`, returns 202 and run payload.  
4. **Orchestrator** runs in order:  
   - **Formalize objectives** — Domain detection, direction, metrics, constraints, `action_ranges`, `initial_state`; merge into `run_spec`, persist.  
   - **Evidence pack** — Build and create evidence pack; select benchmarks; optionally **model_causes** (MoE).  
   - **Scenario generation** — At least 50 scenarios (grid/LHS/random/boundary), each with state, actions, fidelity, seed, `scenario_hash`; persist scenarios and instances.  
   - **Optimization loop** (until convergence or budget):  
     - Propose next batch (optimizer)  
     - Cache lookup by scenario hash  
     - Execute uncached scenarios via Sim Fabric (Ray → domain pack `simulate()`)  
     - Persist metric results  
     - Judge score outcomes  
     - Update optimizer, check convergence  
   - **Finalists** — Promote top scenarios to higher fidelity; robustness scenarios; aggregate results; persist report artifact; seal run; update status to completed.  
5. **Client** receives progress via SSE (`GET /api/runs/{id}/stream`) and polling (`GET /api/runs/{id}`): stages, counters, candidates, `current_best`, then `run_completed`.

### 3.2 Evidence Flow

1. User uploads document → Evidence service.  
2. Text extracted (PDF/DOCX/text), chunked, embedded (e.g. sentence-transformers).  
3. Chunks and embeddings stored in Milvus.  
4. Search queries embedded and matched; relevant chunks returned with scores.

### 3.3 Key File References

| Purpose | File(s) |
|---------|---------|
| API entry, run creation | `services/api/main.py`, `services/api/routers/runs.py` |
| Question → formal spec | `services/orchestrator/activities/formalizer.py`, `services/orchestrator/activities/pipeline.py` (`formalize_objectives`) |
| Full run workflow | `services/orchestrator/workflows/simulation_run.py` |
| Scenario generation | `services/orchestrator/activities/pipeline.py` (`generate_structured_scenarios`) |
| Simulation execution | `services/sim_fabric/executor.py`, `compute/domain_packs/` |
| Optimization loop | `services/orchestrator/activities/optimization.py`, `services/optimizer/` |
| Scoring | `services/judge/` |

---

## 4. Objective Formalization

### 4.1 Input and Output

- **Input:** User prompt (e.g. "Maximize my portfolio returns while keeping risk low"), optional domain hint.  
- **Output:** Structured `FormalizedObjective`: description, metrics (name, direction, weight), primary_direction, constraints, horizon, context_tags, action_ranges, initial_state, domain_hints.

### 4.2 Implementation

- **Domain detection:** Keyword scoring against `DOMAIN_KEYWORDS` (finance-pack, spatial-pack, toy-pack); highest-scoring domain selected.  
- **Direction detection:** `MINIMIZE_KEYWORDS` vs `MAXIMIZE_KEYWORDS` to set primary_direction.  
- **Metric selection:** `DOMAIN_METRICS[domain]` with optional focus (e.g. "return", "risk", "sharpe" for finance).  
- **Constraint extraction:** Pattern matching for budget, time, risk, feasibility.  
- **Optional LLM enhancement:** OpenAI-compatible API call for richer parsing; fallback to heuristic-only if unavailable.  

Location: `services/orchestrator/activities/formalizer.py`, `services/orchestrator/activities/pipeline.py`.

---

## 5. Scenario Generation

### 5.1 Requirements

- Minimum 50 scenarios per run.  
- Diverse coverage: grid (e.g. 20%), Latin hypercube (e.g. 30%), random (e.g. 40%), boundary (e.g. 10%).  
- Deterministic: same seed policy → same scenario set.  
- Each scenario: run_id, state, actions, fidelity, seed, scenario_hash, generation_strategy.

### 5.2 Scenario Hash

Hash input: run_id, state, actions, seed, fidelity (and any other inputs to the simulation). SHA-256 used for caching and reproducibility verification.

### 5.3 Persistence

Scenarios and scenario_instances persisted via orchestrator persistence activities; stored in PostgreSQL (run ledger).

---

## 6. Domain Packs and Simulation Contract

### 6.1 Contract (compute/domain_packs/sdk/base.py)

Every domain pack implements:

```python
class DomainPackBase:
    def state_schema(self) -> Type[BaseModel]
    def action_schema(self) -> Type[BaseModel]
    def simulate(state, actions, fidelity, seed, scenario_id, run_id) -> OutcomeBundle
    def score(outcome, objectives) -> MetricBundle
    def feasibility(state, actions) -> FeasibilityResult
    def cost_model(fidelity) -> CostEstimate
```

### 6.2 Fidelity Modes

- **CHEAP:** Fast approximation (e.g. 10–100 ms); initial exploration.  
- **MID:** Standard precision (e.g. 100–500 ms); optimization iterations.  
- **HIGH:** Full accuracy (e.g. 500 ms–2 s); final ranking.

### 6.3 Implemented Packs

- **ToyPack:** 2D random walk; testing.  
- **FinancePack:** Portfolio backtest (e.g. SPY/BND/GLD/CASH); Sharpe, total return, max drawdown; fidelity affects granularity (monthly/weekly/daily).  
- **SpatialPack:** 2D grid diffusion; coverage, concentration, safe area, threshold violations.

### 6.4 Registry

`compute/domain_packs/sdk/registry.py` — creates pack instances by name/version. Packs registered via decorator `@DomainPackRegistry.register`.

---

## 7. Sim Fabric (Execution Layer)

### 7.1 Role

- Ray-based distributed execution.  
- Worker pools load domain packs and run `simulate(state, actions, fidelity, seed, scenario_id, run_id)`.  
- Caching (e.g. Redis) by scenario hash.  
- Invariant checks (e.g. NaN/Inf, bounds).  
- Optional tracing and artifact storage (MinIO).

### 7.2 Location

`services/sim_fabric/executor.py` — SimulationWorker Ray actor; batch execution; result persistence.

---

## 8. Judge Service

### 8.1 Role

- **Deterministic scoring:** Rubric weights, threshold-based metric scoring, weighted aggregation, constraint penalties.  
- **Benchmark comparison:** Context-based benchmark selection; pass/fail or contribution to score.  
- **No LLM in numbers:** LLM used only for explanation after scoring, not for producing scores or metrics.

### 8.2 Score Composition

Conceptually:  
`final_score = raw_aggregate × feasibility_multiplier × (1 - total_penalty) - constraint_penalty`  
with per-metric contributions and breakdown stored for audit.

---

## 9. Optimizer

### 9.1 Algorithms

- **Bayesian optimization:** Gaussian Process surrogate, Expected Improvement acquisition.  
- **NSGA-II:** Evolutionary multi-objective (Pareto frontier).  
- **Thompson sampling:** Multi-fidelity allocation (cheap vs mid vs high).

### 9.2 Integration

Orchestrator calls: initialize_optimizer, propose_next_batch, update_optimizer, check_convergence. Optimizer state persisted per step for replay and audit.

---

## 10. Run Ledger (Truth Spine)

### 10.1 PostgreSQL Tables (Representative)

- **runs:** id, project_id, org_id, status, run_spec (JSONB), created_at, updated_at, completed_at.  
- **scenarios:** id, run_id, scenario_hash, input_state, actions, fidelity, seed, generation_strategy.  
- **scenario_instances:** id, scenario_id, status, started_at, completed_at.  
- **metric_results:** scenario_instance_id, metric_name, metric_value, unit.  
- **judge_scores:** scenario_instance_id, rubric_version_id, score, breakdown (JSONB).  
- **artifacts:** run_id, artifact_type, storage_key (MinIO), checksum.

### 10.2 Immutability and Provenance

- Run specification hashed and stored.  
- Scenario hashes and seeds recorded.  
- Artifact checksums in MinIO metadata.  
- Domain pack name and version recorded in run_spec.

---

## 11. Security Model

- **Authentication:** JWT (e.g. HS256, configurable expiry).  
- **Authorization:** RBAC (e.g. admin, analyst, viewer); tenant isolation at data layer.  
- **Audit:** Audit events for privileged actions (actor, entity, action, before/after, timestamp).  
- **Versioned rubrics:** Rubric changes with approval and audit.

---

## 12. Observability

- **Tracing:** OpenTelemetry across API → orchestrator → sim fabric → judge/evidence (as designed).  
- **Metrics:** Prometheus endpoints for latency, throughput, errors, queue depth.  
- **Logging:** Structured logs; correlation IDs for run_id/workflow_id.  
- **Dashboards:** Grafana (referenced in quickstart) for SLOs.

---

## 13. Quality Gates (Summary)

From `docs/QUALITY_GATES.md`:

- **Reproducibility:** Deterministic replay; hashed configs; seed policy and scenario seeds recorded.  
- **Evidence:** Benchmarks and rubrics have sources; reports cite EvidencePack chunk IDs.  
- **Simulation:** Invariants and sanity checks; constraint evaluation per scenario.  
- **Optimization:** Beats baseline on ToyPack; no leakage on FinancePack.  
- **Judge:** Deterministic scoring; context-based benchmark selection; full score breakdown.  
- **Security:** RBAC for admin; audit events for edits.  
- **Observability:** Traces across services; metrics dashboards.  
- **UI:** Scenario compare, Pareto view, masked heatmaps with legends/toggles.

---

## 14. Configuration and Assumptions

From `docs/assumptions.md` (abbreviated):

- LLM: OpenAI-compatible API; MoE tiers (FAST/STANDARD/ADVANCED).  
- Embeddings: e.g. all-MiniLM-L6-v2, 384 dims; Milvus, cosine.  
- Temporal: namespace gsip-default, task queue gsip-main.  
- Ray: e.g. 4 workers locally.  
- MinIO: gsip-artifacts, gsip-evidence.  
- Seeds: user or deterministic; run budget default 1000; timestamps UTC; JWT auth; tenant isolation; PostgreSQL 15+; Milvus; three fidelity modes; deterministic scoring only; evidence chunk size/overlap; activity timeouts.

---

## 15. Deployment Topology

- **Containers (infra/docker-compose.yml):** PostgreSQL (5433:5432), Redis (6379), MinIO (9000, 9001), Temporal (7233), Ray (10001, 8265), Milvus (19530).  
- **Application services:** Run separately (API, orchestrator worker, judge, evidence, Sim Fabric workers) with appropriate env (DB, Redis, Temporal, Ray, MinIO, Milvus endpoints).  
- **Frontend:** Next.js dev (3000, 3001) or production build; API base URL configurable.

---

## 16. Testing

- **Smoke e2e (`tests/test_smoke_e2e.py`):** Different prompts → different objectives; different objectives → different rankings; runs have scenarios and metric results; same seed → reproducible outputs.  
- **Unit/integration:** test_api_crud, test_domain_packs, test_evidence, test_ledger, test_moe, test_optimizer, test_scoring, test_sim_fabric.  
- **Determinism:** Seeded replays and scenario hash verification.

---

## 17. Glossary

- **Domain pack:** Pluggable module defining state schema, action schema, simulation, and scoring for a domain.  
- **Fidelity:** Simulation accuracy level (CHEAP, MID, HIGH).  
- **ObjectiveSpec / FormalizedObjective:** Structured objectives and constraints from natural language.  
- **OutcomeBundle:** Result of one simulation (final state, trajectory, timing).  
- **Run ledger:** Immutable audit trail in PostgreSQL.  
- **Scenario:** State, actions, fidelity, seed combination.  
- **Scenario hash:** SHA-256 of scenario inputs for cache and reproducibility.

---

## 18. References

- Project docs: `docs/architecture.md`, `docs/simulation-architecture-overview.md`, `docs/assumptions.md`, `docs/QUALITY_GATES.md`, `docs/DEFINITION_OF_DONE.md`, `HOW_IT_WORKS.md`.  
- Research narrative: `docs/GSIP_Research_Paper_Final.md`.  
- Temporal: https://temporal.io/  
- Ray: https://ray.io/

---

*End of Technical Report*
