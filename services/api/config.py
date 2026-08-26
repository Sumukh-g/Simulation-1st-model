"""API Gateway configuration."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """API gateway settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://gsip:gsip_password@localhost:5433/gsip"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    CORS_ALLOW_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    LOG_LEVEL: str = "INFO"

    # Local demo: if X-User-Id is omitted, resolve admin@gsip.local from seed data.
    # Set GSIP_DEMO_AUTH=false in production.
    GSIP_DEMO_AUTH: bool = True
    DEMO_USER_EMAIL: str = "admin@gsip.local"
    DEMO_ORG_SLUG: str = "gsip-demo"

    # /debug/* endpoints invoke the LLM committee with caller-supplied input.
    # They require authentication, and can be fully disabled in production.
    ENABLE_DEBUG_ENDPOINTS: bool = True


settings = Settings()
