"""GSIP Judge Service - FastAPI Application."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from .config import settings
from .routers import scoring, benchmarks

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan."""
    logger.info("Starting GSIP Judge Service")
    yield
    logger.info("Shutting down GSIP Judge Service")


app = FastAPI(
    title="GSIP Judge Service",
    description="Deterministic scoring engine with expert benchmarks",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Routers
app.include_router(scoring.router, prefix="/score", tags=["Scoring"])
app.include_router(benchmarks.router, prefix="/benchmarks", tags=["Benchmarks"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "gsip-judge"}
