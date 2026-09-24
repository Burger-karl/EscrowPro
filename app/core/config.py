from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql+psycopg://paywork:paywork@localhost:5432/paywork"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Payment Webhook Signature
    WEBHOOK_SECRET: str

    # Firestore
    FIRESTORE_PROJECT_ID: str = "paywork-escrowpro"
    GOOGLE_APPLICATION_CREDENTIALS: str | None = None
    FIRESTORE_CREDENTIALS_JSON: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()