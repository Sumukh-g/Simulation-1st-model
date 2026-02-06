# GSIP API Gateway

FastAPI gateway that enforces authentication and RBAC, then routes requests to
core services (orchestrator, judge, evidence, and sim fabric).

## Responsibilities

- JWT authentication and user/session management
- Role-based access control for admin and policy endpoints
- Run CRUD and lifecycle orchestration
- Audit event emission for all admin edits
- Metrics endpoint for Prometheus

## Entry Point

- `main.py` - FastAPI application setup
- `routers/` - Health, auth, runs, admin, and system routes

## Related Components

- MoE committee: `services/api/moe/`
- Orchestrator: `services/orchestrator/`
