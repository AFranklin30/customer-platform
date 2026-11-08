"""Runtime configuration loaded from the environment."""

from __future__ import annotations

import logging
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration.

    Database credentials come from DATABASE_URL. There is no default URL, so
    the app cannot boot against an accidental embedded database.
    """

    database_url: str
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def database_url_must_use_psycopg(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError(
                "DATABASE_URL must start with postgresql+psycopg:// "
                "so SQLAlchemy uses the psycopg v3 driver."
            )
        return value

    @field_validator("log_level")
    @classmethod
    def log_level_must_be_known(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in logging.getLevelNamesMapping():
            raise ValueError(f"LOG_LEVEL must be a Python logging level, got {value!r}.")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
