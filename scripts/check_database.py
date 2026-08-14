#!/usr/bin/env python
"""
Verify the database is in the state the platform expects.

Run after `alembic upgrade head`. Checks three things:

  * the connection works and the migration actually ran (alembic_version);
  * the tables the run ledger depends on exist;
  * the pgvector extension can be created, since retrieval at launch is
    pgvector-on-Postgres.

Usage:
    DATABASE_URL=postgresql+asyncpg://... python scripts/check_database.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Tables the audit trail and pack registry are built on. Not exhaustive: this is
# a smoke check that the migration produced the schema, not a schema assertion.
REQUIRED_TABLES = (
    "runs",
    "scenarios",
    "audit_events",
    "domain_packs",
    "domain_pack_versions",
    "optimizer_steps",
)

DEFAULT_URL = "postgresql+asyncpg://gsip:gsip_password@localhost:5433/gsip"


async def check(database_url: str) -> list[str]:
    """Return a list of problems; empty means everything passed."""
    problems: list[str] = []
    engine = create_async_engine(database_url, pool_pre_ping=True)

    try:
        async with engine.connect() as connection:
            version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            if not version:
                problems.append("alembic_version is empty; migrations have not been applied")
            else:
                print(f"migration head: {version}")

            rows = await connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            present = {row[0] for row in rows}
            print(f"tables present: {len(present)}")

            missing = [name for name in REQUIRED_TABLES if name not in present]
            if missing:
                problems.append(f"missing expected tables: {', '.join(missing)}")

        # A separate transaction: creating an extension needs its own commit and
        # must not roll back the checks above.
        async with engine.begin() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            installed = await connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
            if installed:
                print(f"pgvector available: {installed}")
            else:
                problems.append("pgvector extension could not be created")
    finally:
        await engine.dispose()

    return problems


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    # Force the async driver; the same URL is often configured for sync tools.
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    print(f"checking {database_url.rsplit('@', 1)[-1]}")

    problems = asyncio.run(check(database_url))
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1

    print("database OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
