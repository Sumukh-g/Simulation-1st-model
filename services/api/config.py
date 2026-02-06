"""API Gateway configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """API gateway settings."""

    DATABASE_URL: str = "postgresql+asyncpg://gsip:gsip_password@localhost:5432/gsip"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    CORS_ALLOW_ORIGINS: list[str] = ["*"]
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()
