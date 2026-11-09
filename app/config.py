"""Runtime configuration loaded from the environment."""

from __future__ import annotations

import logging
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.database_url import build_database_url


class Settings(BaseSettings):
    """Process configuration.

    A host process sets DATABASE_URL. Compose does not. It sets POSTGRES_USER,
    POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, and POSTGRES_DB, and the
    URL is built from those fields. When DATABASE_URL is present it wins, so a
    host URL cannot be replaced by Compose variables that happen to be in the
    same environment.
    """

    database_url: str | None = None
    log_level: str = "INFO"
    postgres_user: str | None = None
    postgres_password: str | None = None
    postgres_host: str | None = None
    postgres_port: int = 5432
    postgres_db: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def blank_database_url_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def database_url_must_use_psycopg(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError(
                "DATABASE_URL must start with postgresql+psycopg:// "
                "so SQLAlchemy uses the psycopg v3 driver."
            )
        return value

    @model_validator(mode="after")
    def resolve_database_url(self) -> Settings:
        if self.database_url:
            return self
        missing = [
            name
            for name, present in (
                ("POSTGRES_USER", bool(self.postgres_user)),
                ("POSTGRES_PASSWORD", self.postgres_password is not None),
                ("POSTGRES_HOST", bool(self.postgres_host)),
                ("POSTGRES_DB", bool(self.postgres_db)),
            )
            if not present
        ]
        if missing:
            raise ValueError("Set DATABASE_URL, or set " + ", ".join(missing) + ".")
        assert self.postgres_user is not None
        assert self.postgres_password is not None
        assert self.postgres_host is not None
        assert self.postgres_db is not None
        self.database_url = build_database_url(
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )
        return self

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
