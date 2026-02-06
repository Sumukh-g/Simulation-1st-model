"""GSIP Evidence Service - FastAPI Application."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from .config import settings
from .routers import ingestion, search, packs, claims

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan."""
    logger.info("Starting GSIP Evidence Service")
    # Initialize embedding model
    from .embeddings import init_embeddings
    init_embeddings()
    yield
    logger.info("Shutting down GSIP Evidence Service")


app = FastAPI(
    title="GSIP Evidence Service",
    description="Document ingestion, embedding, and semantic search",
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
app.include_router(ingestion.router, prefix="/ingest", tags=["Ingestion"])
app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(packs.router, prefix="/packs", tags=["Evidence Packs"])
app.include_router(claims.router, prefix="/claims", tags=["Claims"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "gsip-evidence"}
