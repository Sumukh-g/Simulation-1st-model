"""Orchestrator Configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Orchestrator settings."""
    
    # Temporal
    TEMPORAL_HOST: str = "localhost:7233"
    TEMPORAL_NAMESPACE: str = "gsip-default"
    TEMPORAL_TASK_QUEUE: str = "gsip-main"
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://gsip:gsip_password@localhost:5432/gsip"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Ray
    RAY_ADDRESS: str = "ray://localhost:10001"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"


settings = Settings()
