# Local run guide (current working state)

## Honest scope

This repo is a **working v1 simulation engine** plus **Phase 1 scaffolding** for on-demand packs.
It is **not** the full v2 grounded product yet (provenance gate, playbooks, Morris triage, pack generator, etc.).

What works today after the latest fixes:

- Docker infra: Postgres + Temporal (+ Redis/MinIO)
- Seed data: org, admin user, Demo Project, `toy-pack` / `finance-pack` / `spatial-pack`
- Demo auth (no headers required locally when `GSIP_DEMO_AUTH=true`)
- `POST /api/runs/start` with `simulation_mode`:
  - `domain_pack` → full Temporal run (formalize → scenarios → simulate → judge → report)
  - `create_pack` → LLM classifies, auto-selects recommended method, drafts ephemeral pack, **runs full simulation**
  - `no_pack` → LLM drafts ephemeral pack, **runs full illustrative simulation** (results labelled ILLUSTRATIVE)
- Gemini uses `GEMINI_MODEL` plus `GEMINI_FALLBACK_MODELS` alternate models before falling back to Groq/OpenAI
- In-process simulation (no Ray cluster required for local demos)
- Web UI proxy + pack name fixes + mode selector + past-run history

---

## What you must do (host machine)

1. **Start Docker Desktop** and wait until it is ready.
2. From the repo root:

```powershell
docker compose -f infra/docker-compose.yml up -d postgres redis minio temporal
cd services/api; alembic upgrade head; cd ../..
python scripts/seed_data.py
```

3. Terminal A — API:

```powershell
$env:RAY_ADDRESS="local"
$env:DATABASE_URL="postgresql+asyncpg://gsip:gsip_password@localhost:5433/gsip"
uvicorn services.api.main:app --reload --host 127.0.0.1 --port 8000
```

4. Terminal B — Temporal worker (required for real runs):

```powershell
$env:RAY_ADDRESS="local"
$env:DATABASE_URL="postgresql+asyncpg://gsip:gsip_password@localhost:5433/gsip"
python -m services.orchestrator.worker
```

5. Optional — Web UI:

```powershell
cd apps/web
npm ci
npm run dev
```

Open http://localhost:3000  
Use the gear icon to pick **Use existing pack** / **Create domain pack** / **No domain pack**.  
Pack names: `toy-pack`, `finance-pack`, `spatial-pack`.

Production build (optional). On a OneDrive/Dropbox-synced checkout, the sync
client can lock files under `.next/cache` and stall `next build`; set the
escape hatch to skip the webpack filesystem cache:

```powershell
cd apps/web
$env:NEXT_DISABLE_WEBPACK_CACHE="1"   # only needed on synced filesystems
npm run build
```

6. Smoke curl (PowerShell):

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/runs/start -Method POST -ContentType "application/json" -Body '{"prompt":"Move closer to the target","domain_pack":"toy-pack","simulation_mode":"domain_pack","config":{"maxScenarios":10}}'
```

---

## What is still incomplete (you / next sessions)

These are the remaining product pieces from the v2 brief and `docs/on_demand_domain_pack_and_no_pack_mode.md`:

| Item | Status |
|------|--------|
| Provenance model + gate wired into workflow | Types only (`core/contract.py`) |
| Classifier + playbooks + method catalog | Not built |
| Create-pack: generate real `simulate()` from chosen method | API accepts mode only |
| No-pack sandboxed AI execution | API accepts mode only |
| Human-in-loop `/clarify` + `/override` | Not built |
| Fidelity descriptor on packs | Not on `DomainPackBase` |
| Pack authoring UI / `gsip new-pack` | Not built |
| Honest confidence report UI | Not built |
| Run counters live update in `run_spec` | Stages update; counters often stay 0 |
| Optional Ray cluster profile | `docker compose --profile ray-cluster` (local mode preferred on Windows) |

Optional for better demos:

- LLM providers (multi-provider, tiered, with fallback + circuit breaker) are
  configured via `.env` at the repo root. Any subset works:
  - `OPENAI_API_KEY` (advanced tier), `GROQ_API_KEY` (fast/standard),
    `GEMINI_API_KEY` (fast). Override models with `OPENAI_MODEL` / `GROQ_MODEL`
    / `GEMINI_MODEL`. For Gemini, set `GEMINI_FALLBACK_MODELS` (comma-separated)
    so alternate Gemini models are tried before leaving the provider.
  - Verify setup without exposing secrets: `python scripts/check_llm.py`
    or `GET /health/llm`. If no provider is reachable, the pipeline falls back
    to deterministic heuristics.
- Set `GSIP_DEMO_AUTH=false` and send real `X-User-Id` / `X-Org-Id` in
  production (the caller must be an active member of the org, or the request is
  rejected with 403). Set `ENABLE_DEBUG_ENDPOINTS=false` to remove `/debug/*`.

---

## Verified in this session

- Python unit tests: **214 passed, 1 skipped** (integration test needs testcontainers)
- Web: **53 vitest tests**, `tsc --noEmit` clean, `next build` succeeds
- `create_pack` / `no_pack` run through Temporal and return candidates + narrative (ephemeral simulator)
