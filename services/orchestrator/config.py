"""Orchestrator Configuration."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Orchestrator settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    # Temporal
    TEMPORAL_HOST: str = "localhost:7233"
    TEMPORAL_NAMESPACE: str = "gsip-default"
    TEMPORAL_TASK_QUEUE: str = "gsip-main"
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://gsip:gsip_password@localhost:5433/gsip"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Ray — local by default for demos; set ray://host:10001 for a cluster
    RAY_ADDRESS: str = "local"
    
    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()
