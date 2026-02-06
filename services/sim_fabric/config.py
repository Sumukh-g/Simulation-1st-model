"""Simulation Fabric Configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Simulation fabric settings."""

    # Ray
    RAY_ADDRESS: str = "ray://localhost:10001"
    RAY_NUM_CPUS: int = 4
    RAY_NUM_GPUS: int = 0

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "gsip-artifacts"

    # Execution
    MAX_CONCURRENT_SIMULATIONS: int = 100
    DEFAULT_TIMEOUT_SECONDS: int = 300
    DEFAULT_POOL_SIZE: int = 4
    DEFAULT_ISOLATION_MODE: str = "none"  # none, subprocess, container

    # Cache
    CACHE_TTL_SECONDS: int = 604800  # 7 days

    # Artifacts
    PREVIEW_TARGET_SIZE: int = 100
    HEATMAP_COLORMAP: str = "viridis"

    # Logging
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()
