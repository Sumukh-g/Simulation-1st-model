# GSIP Architecture

## Overview

The General Simulation Intelligence Platform (GSIP) is a decision-laboratory web application that:
1. Converts user goals into formal objectives and constraints
2. Generates structured scenario spaces
3. Runs simulations at multiple fidelities
4. Optimizes via systematic search
5. Applies expert judgment with deterministic scoring
6. Produces defensible outputs with full audit trails

For a step-by-step description of how a user question flows through the system (formalization, scenario generation, simulation, scoring, optimization), see [simulation-architecture-overview.md](simulation-architecture-overview.md).

## System Architecture

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
│                      │ │                  │ │                          │
│   - Workflows        │ │   - Scoring      │ │   - Ingestion            │
│   - Activities       │ │   - Benchmarks   │ │   - Embeddings           │
│   - State Machine    │ │   - Rubrics      │ │   - Search               │
└──────────────────────┘ └──────────────────┘ └──────────────────────────┘
          │                                              │
          ▼                                              ▼
┌──────────────────────┐                    ┌──────────────────────────┐
│   Sim Fabric         │                    │   Milvus Vector DB       │
│   (Ray Cluster)      │                    │   (port 19530)           │
│                      │                    │                          │
│   - Worker Pools     │                    │   - Embeddings           │
│   - Domain Packs     │                    │   - Similarity Search    │
│   - Distributed Exec │                    │                          │
└──────────────────────┘                    └──────────────────────────┘
          │
          ▼
┌──────────────────────┐
│   Optimizer          │
│                      │
│   - Bayesian         │
│   - Evolutionary     │
│   - Multi-fidelity   │
└──────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                           Storage Layer                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐    │
│  │PostgreSQL│  │  MinIO   │  │  Redis   │  │       Temporal       │    │
│  │  (5432)  │  │  (9000)  │  │  (6379)  │  │       (7233)         │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. API Gateway (FastAPI)

Central entry point for all client requests:
- Authentication via JWT
- Role-based access control
- Request routing to services
- Prometheus metrics endpoint

### 2. Orchestrator (Temporal)

Durable workflow engine:
- `SimulationRunWorkflow`: Complete run execution
- `OptimizationLoopWorkflow`: Iterative optimization
- Automatic retries and state persistence

### 3. Simulation Fabric (Ray)

Distributed execution:
- Worker pools per domain pack
- Multi-fidelity scheduling
- Deterministic replay

### 4. Optimizer

Search algorithms:
- Bayesian optimization with GP surrogate
- NSGA-II evolutionary multi-objective
- Thompson sampling for fidelity allocation

### 5. Judge Service

Deterministic scoring:
- Rubric-based evaluation
- Benchmark comparison
- LLM explanation (post-scoring only)

### 6. Evidence Service

Document processing:
- PDF, DOCX, text ingestion
- Sentence-transformer embeddings
- Milvus vector search

### 7. MoE Committee

Structured expert system:
- Task routing
- Expert contracts (JSON in/out)
- Arbitration and escalation

## Data Flow

### Run Execution Flow

```
1. User creates run → API validates → Store in Postgres
2. API triggers Temporal workflow
3. Orchestrator generates scenarios
4. Scenarios dispatched to Ray workers
5. Workers load domain pack, execute simulations
6. Results scored by Judge service
7. Optimizer proposes next batch (if optimization run)
8. Results aggregated, run sealed
9. Artifacts stored in MinIO with checksums
```

### Evidence Flow

```
1. User uploads document → Evidence service
2. Text extracted → Chunked → Embedded
3. Chunks + embeddings stored in Milvus
4. Search queries embedded and matched
5. Relevant chunks returned with scores
```

## Domain Pack Contract

Every domain pack implements:

```python
class DomainPackBase:
    def state_schema(self) -> Type[BaseModel]
    def action_schema(self) -> Type[BaseModel]
    def simulate(state, actions, fidelity, seed) -> OutcomeBundle
    def score(outcome, objectives) -> MetricBundle
    def feasibility(state, actions) -> FeasibilityResult
    def cost_model(fidelity) -> CostEstimate
```

## Run Ledger (Truth Spine)

Immutable audit trail:
- Run specification hash
- Scenario hashes
- Seed policy
- Artifact checksums
- Version information

## Security Model

- JWT authentication
- Tenant isolation
- RBAC (admin, analyst, viewer)
- Audit logging
- Versioned rubrics with approval

## Observability

- OpenTelemetry tracing
- Prometheus metrics
- Grafana dashboards
- Structured logging
