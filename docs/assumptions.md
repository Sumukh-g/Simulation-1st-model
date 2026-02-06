# GSIP Design Assumptions

This document records key design assumptions made during the development of the General Simulation Intelligence Platform.

## 1. LLM Configuration

- **Assumption**: LLM calls use an OpenAI-compatible API endpoint
- **Default**: `https://api.openai.com/v1`
- **Rationale**: OpenAI API is the de facto standard; other providers (Azure, Anthropic, local) can be adapted

## 2. MoE Model Tiers

- **Assumption**: Three tiers of LLM capability
  - FAST: GPT-3.5-turbo or equivalent (simple routing, quick tasks)
  - STANDARD: GPT-4 or equivalent (most tasks)
  - ADVANCED: GPT-4 Turbo or equivalent (complex, high-stakes)
- **Rationale**: Balance cost, latency, and capability

## 3. Evidence Embeddings

- **Assumption**: Use `all-MiniLM-L6-v2` for embedding generation
- **Dimension**: 384
- **Rationale**: Good balance of quality and speed; widely available

## 4. Temporal Configuration

- **Namespace**: `gsip-default`
- **Task Queue**: `gsip-main`
- **Rationale**: Single namespace for simplicity in initial deployment

## 5. Ray Cluster

- **Assumption**: Starts with 4 workers locally
- **Rationale**: Reasonable default for local development; scales in production

## 6. MinIO Storage

- **Bucket**: `gsip-artifacts` for simulation outputs
- **Bucket**: `gsip-evidence` for document storage
- **Rationale**: Separate concerns while using same storage backend

## 7. Timestamps

- **Assumption**: All timestamps are stored in UTC
- **Rationale**: Consistent timezone handling across distributed system

## 8. Seed Policy

- **Assumption**: Seeds are user-provided or auto-generated deterministically
- **Default Auto**: Based on timestamp hash at run creation
- **Rationale**: Ensures reproducibility while allowing flexibility

## 9. Run Budget

- **Default**: 1000 simulations per run
- **Rationale**: Reasonable default; can be overridden per run

## 10. Heatmap Resolution

- **Default**: 100x100 grid
- **Rationale**: Balance of detail and performance

## 11. Authentication

- **Assumption**: JWT-based authentication
- **Algorithm**: HS256
- **Expiry**: 24 hours
- **Rationale**: Standard, stateless authentication

## 12. Multi-tenancy

- **Assumption**: Tenant isolation at database level
- **Rationale**: Simpler than schema-per-tenant for initial version

## 13. Fidelity Modes

- **Assumption**: Three standard modes: cheap, mid, high
- **Rationale**: Universal abstraction across domain packs

## 14. Scoring

- **Assumption**: All scoring is deterministic mathematical computation
- **Rationale**: LLMs must not influence numerical results

## 15. Evidence Chunking

- **Default Chunk Size**: 512 characters
- **Default Overlap**: 50 characters
- **Rationale**: Balance of context preservation and retrieval precision

## 16. Database

- **Assumption**: PostgreSQL 15+ with JSONB support
- **Rationale**: Robust, supports complex queries and JSON operations

## 17. Vector Database

- **Assumption**: Milvus for vector storage
- **Collection**: `gsip_evidence`
- **Metric**: Cosine similarity
- **Rationale**: Production-grade vector database with good Python support

## 18. Workflow Timeouts

- **Activity Default**: 30 minutes
- **Scenario Generation**: 10 minutes
- **Simulation Batch**: 30 minutes
- **Rationale**: Conservative defaults; can be tuned per use case

## 19. Constraint Handling

- **Assumption**: Constraints are soft by default (penalties, not rejections)
- **Rationale**: Allows exploration of constraint boundaries

## 20. Pareto Frontier

- **Assumption**: For multi-objective, track full Pareto frontier
- **Rationale**: Users may want different trade-off points

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2024-01-30 | 1.0 | Initial assumptions documented |
