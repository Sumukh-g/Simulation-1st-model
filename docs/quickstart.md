# GSIP Quickstart Guide

Get the General Simulation Intelligence Platform running locally in minutes.

## Prerequisites

- Docker & Docker Compose
- Node.js 20+
- Python 3.11+
- pnpm 8+

## Quick Start

### 1. Clone and Setup

```bash
cd gsip
cp .env.example .env
```

### 2. Start Infrastructure

```bash
cd infra
docker-compose up -d
```

This starts:
- PostgreSQL (5432)
- Redis (6379)
- MinIO (9000/9001)
- Temporal (7233)
- Temporal UI (8080)
- Ray (10001/8265)
- Milvus (19530)
- Prometheus (9090)
- Grafana (3002)

### 3. Run Database Migrations

```bash
cd services/api
poetry install
alembic upgrade head
```

### 4. Load Seed Data

```bash
python scripts/seed_data.py
```

### 5. Start Backend Services

In separate terminals:

```bash
# API Gateway
cd services/api
uvicorn main:app --reload --port 8000

# Orchestrator Worker
cd services/orchestrator
python -m worker

# Judge Service
cd services/judge
uvicorn main:app --reload --port 8001

# Evidence Service
cd services/evidence
uvicorn main:app --reload --port 8002
```

### 6. Start Frontend

```bash
# Main Web App
cd apps/web
pnpm install
pnpm dev

# Admin Dashboard (optional)
cd apps/admin
pnpm install
pnpm dev
```

### 7. Access the Platform

- **Web App**: http://localhost:3000
- **Admin**: http://localhost:3001
- **API Docs**: http://localhost:8000/docs
- **Temporal UI**: http://localhost:8080
- **Ray Dashboard**: http://localhost:8265
- **Grafana**: http://localhost:3002 (admin/admin)
- **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin)

## First Run

### 1. Create a User

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password", "name": "Test User"}'
```

### 2. Get Auth Token

```bash
curl -X POST http://localhost:8000/auth/token \
  -d "username=user@example.com&password=password"
```

### 3. Create a Run

```bash
TOKEN="your-token-here"

curl -X POST http://localhost:8000/runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My First Run",
    "domain_pack_id": "toy-pack-v1",
    "objective_spec": {"type": "minimize", "metrics": ["distance_to_target"]},
    "budget": 100
  }'
```

### 4. Check Run Status

```bash
curl http://localhost:8000/runs/{run_id} \
  -H "Authorization: Bearer $TOKEN"
```

## Next Steps

- Read the [Architecture Guide](architecture.md)
- Explore [Domain Packs](../compute/domain_packs/)
- Review [Assumptions](assumptions.md)
- Check out the [API Documentation](http://localhost:8000/docs)
