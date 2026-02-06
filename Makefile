.PHONY: help install dev test lint format clean docker-up docker-down migrate seed

help:
	@echo "GSIP Development Commands"
	@echo ""
	@echo "  install     - Install all dependencies"
	@echo "  dev         - Start development servers"
	@echo "  test        - Run all tests"
	@echo "  lint        - Run linters"
	@echo "  format      - Format code"
	@echo "  clean       - Clean build artifacts"
	@echo "  docker-up   - Start Docker infrastructure"
	@echo "  docker-down - Stop Docker infrastructure"
	@echo "  migrate     - Run database migrations"
	@echo "  seed        - Load seed data"

install:
	pnpm install
	cd services/api && poetry install
	cd services/orchestrator && poetry install
	cd services/judge && poetry install
	cd services/evidence && poetry install
	cd services/optimizer && poetry install

dev:
	@echo "Starting development servers..."
	@echo "Run these in separate terminals:"
	@echo "  1. cd infra && docker-compose up -d"
	@echo "  2. cd services/api && uvicorn main:app --reload"
	@echo "  3. cd apps/web && pnpm dev"

test:
	pytest tests/ -v --cov=services --cov=libs --cov=compute

lint:
	ruff check services/ libs/ compute/
	cd apps/web && pnpm lint
	cd apps/admin && pnpm lint

format:
	black services/ libs/ compute/
	ruff check --fix services/ libs/ compute/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true

docker-up:
	cd infra && docker-compose up -d

docker-down:
	cd infra && docker-compose down

migrate:
	cd services/api && alembic upgrade head

seed:
	python scripts/seed_data.py
