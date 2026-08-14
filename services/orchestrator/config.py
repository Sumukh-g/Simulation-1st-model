"""Orchestrator Configuration."""
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Orchestrator settings."""
    
    model_config = ConfigDict(extra="ignore")
    
    # Temporal
    TEMPORAL_HOST: str = "localhost:7233"
    TEMPORAL_NAMESPACE: str = "gsip-default"
    TEMPORAL_TASK_QUEUE: str = "gsip-main"
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://gsip:gsip_password@localhost:5433/gsip"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Ray
    RAY_ADDRESS: str = "ray://localhost:10001"
    
    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()
