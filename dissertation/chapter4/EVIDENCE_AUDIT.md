# Evidence audit

Date of campaign: 27 August 2026. Commit under test: `7803baa721a12ca19e26e700425fe7be94bfc3a4`. Application source was not modified.

## Directly verified

| Item | Evidence | Status |
|---|---|---|
| Python unit suite | `logs/pytest.txt` | 223 passed, 1 skipped, 0 failed, 64.86 s, coverage 56% |
| Ruff | `logs/ruff_plain.txt`, `logs/ruff.txt` | 3 style errors; not treated as test failures |
| Web Vitest | `logs/web-vitest.txt` | 55 passed, 5 files, 2.46 s |
| Admin Vitest | `logs/admin-vitest.txt` | No test files; exit 1 |
| Alembic + pgvector | `logs/alembic.txt`, `logs/check_database.txt` | Head `0001_initial`; 41 tables; pgvector 0.6.0 |
| Seed | `logs/seed_data.txt` | Demo Project loaded |
| Equal-budget optimiser campaign | `evidence/benchmark_campaign.json`, `benchmark_runs.csv`, `benchmark_stats.json` | 120/120 completed; budget 200; seeds 1-10 |
| Same-seed replay | `benchmark_stats.json` `replay.same_seed` | Exact HV/IGD/front/history match at budget 60, seed 123 (both HV 0.0) |
| Changed-seed check | `replay.changed_seed` | Fronts and IGD differed (123 vs 124) |
| In-process domain-pack runs | `evidence/ui_inprocess_runs.json`, `run_*-pack.pdf` | ToyPack, SpatialPack, FinancePack persisted without Temporal |
| UI screenshots | `screenshots/*.png` (31 files) | Web, admin (mock data), OpenAPI `/docs` |
| Figures | `figures/figure_4_*.png` | Generated from campaign JSON only |
| GitHub Actions | run 33028242616 on 7803baa | Tests 3.11/3.12, web, migrations, Docker image success; lint failure |

## Treated as context, not results

- `docs/LOCAL_RUN.md` (214 tests; this session recorded 223)
- Phase 0 optimiser smoke table (different n, not reused)
- `docs/optimiser-benchmark-findings.md` (used only to locate the hybrid GP defect in source, then confirmed experimentally)
- Research-paper markdown under `docs/` (contains fabricated statistics; not reused)

## Not verified

See `UNVERIFIABLE_ITEMS.md`.
