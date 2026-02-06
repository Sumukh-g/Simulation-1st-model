"""GSIP API Gateway - FastAPI Application."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from .config import settings
from .routers import admin, debug, health, runs

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger(__name__)

app = FastAPI(
    title="GSIP API Gateway",
    description="Authentication, RBAC, and service routing",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Routers
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(debug.router, prefix="/debug", tags=["Debug"])
app.include_router(runs.router, prefix="/api", tags=["Runs"])


@app.get("/")
async def root():
    return {"service": "gsip-api", "status": "ok"}
