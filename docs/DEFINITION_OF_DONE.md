# Definition of Done (DoD)

A feature, experiment, or release is **Done** only when all applicable items
below are complete and verified.

## 1. Scope and Documentation

- Acceptance criteria are met and recorded in the run or feature spec.
- User-facing documentation is updated (API docs, UI flows, or ops notes).
- Assumptions or constraints are added to `docs/assumptions.md` when needed.

## 2. Quality Gates (Must Pass)

Each gate is defined in `docs/QUALITY_GATES.md` and must be verified.

- **Reproducibility Gate:** deterministic replay, hashed configs, documented
  seed policy with recorded scenario seeds.
- **Evidence Gate:** benchmarks and rubrics include sources; reports cite
  `EvidencePack` chunk IDs.
- **Simulation Gate:** invariants, sanity checks, and constraint evaluation are
  enforced and logged.
- **Optimization Gate:** beats baseline on `ToyPack` and does not leak on
  `FinancePack`.
- **Judge Gate:** deterministic scoring, context-based benchmark selection, and
  full score breakdown.
- **Security Gate:** RBAC for admin actions and audit events for every edit.
- **Observability Gate:** traces across services and metrics dashboards for key
  SLOs.
- **UI Gate:** scenario compare, Pareto view, and masked heatmaps with legends
  and toggles.

## 3. Testing and Verification

- Unit and integration tests cover the new behavior and edge cases.
- Determinism tests are executed where applicable (seeded replays).
- Data validation tests cover schema, invariants, and constraints.

## 4. Operational Readiness

- Configuration defaults are safe and documented.
- Rollback or disablement strategy is documented for risky changes.
- Service-level dashboards and alerts are updated if the change affects
  latency, throughput, or reliability.

## 5. Release Artifacts

- Versioning and changelog entries are updated when required.
- Deployment configs (including `infra/docker-compose.yml`) reflect the new
  dependency needs.
