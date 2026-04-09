from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Backend Test Task"
    secret_key: str = Field(default="change-me-change-me-change-me-change-me")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    database_url: str = Field(default="postgresql+asyncpg://app:app@localhost:5432/app")
    redis_url: str = Field(default="redis://localhost:6379/0")


@lru_cache
def get_settings() -> Settings:
    return Settings()
