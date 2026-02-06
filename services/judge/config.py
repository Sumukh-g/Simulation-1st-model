"""Judge Service Configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Judge service settings."""
    
    DATABASE_URL: str = "postgresql+asyncpg://gsip:gsip_password@localhost:5432/gsip"
    REDIS_URL: str = "redis://localhost:6379/0"
    LOG_LEVEL: str = "INFO"
    
    # LLM for explanations (not for scoring)
    LLM_API_BASE: str = "https://api.openai.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-3.5-turbo"
    
    class Config:
        env_file = ".env"


settings = Settings()
