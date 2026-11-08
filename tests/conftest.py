"""Pytest setup for a real PostgreSQL database.

Tests never use the development database. The database name must end with
`_test`. Tables are truncated before and after every test.
"""

from __future__ import annotations

import getpass
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _resolve_test_database_url() -> str:
    configured = os.environ.get("TEST_DATABASE_URL")
    if configured:
        return configured

    existing = os.environ.get("DATABASE_URL")
    if existing and (make_url(existing).database or "").endswith("_test"):
        return existing

    user = os.environ.get("PGUSER", getpass.getuser())
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    return f"postgresql+psycopg://{user}@{host}:{port}/customer_platform_test"


def _ensure_database(url: str) -> None:
    target = make_url(url)
    database_name = target.database
    if database_name is None or re.fullmatch(r"[A-Za-z0-9_]+", database_name) is None:
        raise RuntimeError(f"Unsupported test database name: {database_name!r}")
    if not database_name.endswith("_test"):
        raise RuntimeError(
            "Refusing to run tests against a database whose name does not end with _test."
        )

    admin_engine = create_engine(
        target.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    with admin_engine.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": database_name},
        ).scalar()
        if exists is None:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    admin_engine.dispose()


TEST_DATABASE_URL = _resolve_test_database_url()
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
_ensure_database(TEST_DATABASE_URL)


def _truncate_tables() -> None:
    from app.database import engine

    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE idempotency_keys, customers"))


import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    from alembic import command
    from alembic.config import Config

    configuration = Config(str(ROOT / "alembic.ini"))
    configuration.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(configuration, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables(migrated_database: None) -> Iterator[None]:
    _truncate_tables()
    yield
    _truncate_tables()
