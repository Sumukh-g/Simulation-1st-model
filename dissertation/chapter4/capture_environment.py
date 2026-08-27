#!/usr/bin/env python3
"""Record the experimental environment. Does not modify application source."""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "evidence"
OUT.mkdir(parents=True, exist_ok=True)


def _run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=ROOT)
        return (result.stdout or result.stderr or "").strip()
    except Exception as exc:  # noqa: BLE001
        return f"[unavailable: {exc}]"


def _which(name: str) -> str | None:
    return shutil.which(name)


def _redact_remote(url: str) -> str:
    """Strip credentials from git remotes before writing evidence."""
    if "github.com/" in url:
        return "https://github.com/" + url.split("github.com/", 1)[1]
    return url


def main() -> int:
    git_status = _run(["git", "status", "--porcelain"])
    payload = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "repository": {
            "commit": _run(["git", "rev-parse", "HEAD"]),
            "commit_short": _run(["git", "rev-parse", "--short", "HEAD"]),
            "branch": _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
            "working_tree_clean": git_status == "",
            "status_porcelain": git_status,
            "remote": _redact_remote(_run(["git", "remote", "get-url", "origin"])),
            "log_head": _run(["git", "log", "-1", "--format=%H %ci %s"]),
        },
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "platform": platform.platform(),
            "os_release": Path("/etc/os-release").read_text(encoding="utf-8")
            if Path("/etc/os-release").exists()
            else None,
        },
        "processor": {
            "lscpu": _run(["lscpu"]),
            "cpu_count": os.cpu_count(),
        },
        "memory": {
            "free": _run(["free", "-h"]),
        },
        "gpu": {
            "nvidia_smi": _run(["nvidia-smi", "-L"]) if _which("nvidia-smi") else "No NVIDIA GPU detected",
        },
        "software": {
            "python": sys.version,
            "python_executable": sys.executable,
            "node": _run(["node", "--version"]),
            "npm": _run(["npm", "--version"]),
            "docker": _run(["docker", "--version"]) if _which("docker") else "not available",
            "docker_compose": _run(["docker", "compose", "version"]) if _which("docker") else "not available",
            "docker_info_error": None,
            "postgres": _run(["psql", "--version"]),
            "redis": _run(["redis-server", "--version"]),
            "libreoffice": _run(["libreoffice", "--version"]),
        },
        "python_packages": _run([sys.executable, "-m", "pip", "freeze"]),
        "commands": {
            "start_services": [
                "sudo service postgresql start",
                "sudo service redis-server start",
                "DATABASE_URL=postgresql+asyncpg://gsip:gsip_password@localhost:5432/gsip alembic upgrade head (services/api)",
                "DATABASE_URL=postgresql+asyncpg://gsip:gsip_password@localhost:5432/gsip python scripts/seed_data.py",
                "DATABASE_URL=postgresql+asyncpg://gsip:gsip_password@localhost:5432/gsip RAY_ADDRESS=local uvicorn services.api.main:app --host 127.0.0.1 --port 8000",
                "cd apps/web && npm run dev",
                "cd apps/admin && npm run dev",
            ],
            "tests": [
                'pytest -m "not integration and not slow" --cov --cov-report=term --cov-report=json --cov-report=xml',
                "ruff check core/ libs/ compute/ services/ scripts/ tests/",
                "cd apps/web && npm test -- --run",
            ],
            "benchmarks": [
                "python dissertation/chapter4/run_benchmark_campaign.py",
            ],
        },
        "environment_variables_material": {
            "DATABASE_URL": "postgresql+asyncpg://gsip:gsip_password@localhost:5432/gsip",
            "RAY_ADDRESS": "local",
            "GSIP_DEMO_AUTH": "true (library default; not overridden)",
            "note": "Local Postgres listens on 5432. The repository default is 5433 for Docker Compose. Secrets were not recorded.",
        },
        "random_seed_policy": "Independent integer seeds 1 to 10 inclusive per backend and problem. Same seed reused for same-seed replay checks.",
        "timeout_retry": "Benchmark runs have no extra timeout beyond library defaults. Temporal retry policy was not exercised because Temporal was not running.",
        "differences_from_submitted_repository": [
            "Experiments ran from commit 7803baa with a clean working tree relative to application source.",
            "Python packages were installed into a local virtualenv at .venv; this path is gitignored.",
            "Docker daemon could not start (overlay2 unsupported in this environment), so Postgres 16 and Redis 7 were used natively instead of the Compose stack (Postgres 15 pgvector image, Temporal, MinIO).",
            "No Temporal, MinIO, Milvus or Ray cluster services were available.",
            "The application source was not modified.",
        ],
    }

    if _which("docker"):
        info = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=20)
        if info.returncode != 0:
            payload["software"]["docker_info_error"] = (info.stderr or info.stdout or "").strip()[:2000]

    path = OUT / "environment.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
