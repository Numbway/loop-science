"""Application configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://rc_user:rc_pass@localhost:5432/research_companion"
    )
    DATABASE_URL_SYNC: str = (
        "postgresql://rc_user:rc_pass@localhost:5432/research_companion"
    )

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    SEMANTIC_SCHOLAR_API_KEY: str = ""
    CREDENTIAL_ENCRYPTION_KEY: str = ""

    # Storage
    STORAGE_PATH: str = "/data/projects"

    # Experiment executor
    EXECUTOR_IMAGE: str = "loop-science-executor:latest"
    EXECUTOR_SANDBOX_MODE: bool = False
    TENSORBOARD_PUBLIC_URL: str = ""

    # JWT
    JWT_SECRET: str = "dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 hours

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
