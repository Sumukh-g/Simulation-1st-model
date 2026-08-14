.PHONY: help install dev test test-all lint format clean docker-up docker-down up down build migrate check-db seed benchmark benchmark-full

help:
	@echo "GSIP Development Commands"
	@echo ""
	@echo "  install       - Install all dependencies"
	@echo "  dev           - How to start development servers"
	@echo "  test          - Run the test suite (excludes integration and slow)"
	@echo "  test-all      - Run everything, including Docker-backed integration tests"
	@echo "  lint          - Run linters"
	@echo "  format        - Format code"
	@echo "  clean         - Clean build artifacts"
	@echo ""
	@echo "  docker-up     - Start infrastructure only (Postgres, Redis, MinIO, Temporal, Ray, Milvus)"
	@echo "  docker-down   - Stop infrastructure"
	@echo "  build         - Build the application container images"
	@echo "  up            - Start infrastructure and application services"
	@echo "  down          - Stop everything"
	@echo ""
	@echo "  migrate       - Run database migrations"
	@echo "  check-db      - Verify schema and pgvector availability"
	@echo "  seed          - Load seed data"
	@echo ""
	@echo "  benchmark     - Prove the optimiser on ZDT1 (minutes)"
	@echo "  benchmark-full- Canonical-size ZDT sweep (long)"

INFRA := -f infra/docker-compose.yml
APPS := -f infra/docker-compose.yml -f infra/docker-compose.apps.yml

install:
	pip install -r requirements-dev.txt
	cd apps/web && npm ci
	cd apps/admin && npm ci

dev:
	@echo "Starting development servers..."
	@echo "Run these in separate terminals:"
	@echo "  1. make docker-up"
	@echo "  2. make migrate"
	@echo "  3. uvicorn services.api.main:app --reload"
	@echo "  4. cd apps/web && npm run dev"

test:
	pytest -m "not integration and not slow"

test-all:
	pytest

lint:
	ruff check core/ libs/ compute/ services/ scripts/ tests/
	cd apps/web && npm run lint
	cd apps/admin && npm run lint

format:
	ruff check --fix core/ libs/ compute/ services/ scripts/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true

docker-up:
	docker compose $(INFRA) up -d

docker-down:
	docker compose $(INFRA) down

build:
	docker compose $(APPS) build

up:
	docker compose $(APPS) up -d

down:
	docker compose $(APPS) down

migrate:
	cd services/api && alembic upgrade head

check-db:
	python scripts/check_database.py

seed:
	python scripts/seed_data.py

benchmark:
	python scripts/run_benchmark.py --spec configs/benchmarks/zdt1_smoke.yaml

benchmark-full:
	python scripts/run_benchmark.py --spec configs/benchmarks/zdt_canonical.yaml \
		--output results/zdt_canonical.json
