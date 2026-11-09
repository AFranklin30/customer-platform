"""URL construction for passwords that contain reserved characters.

These tests do not connect to PostgreSQL. They check encoding and which
configuration source is used.
"""

from __future__ import annotations

from configparser import ConfigParser

import pytest
from pydantic import ValidationError
from sqlalchemy.engine.url import make_url

from app.config import Settings
from app.database_url import build_database_url, escape_for_configparser

SPECIAL_PASSWORD = "p@ss:w/rd#1%"


def test_special_characters_round_trip_through_sqlalchemy_url() -> None:
    rendered = build_database_url(
        username="customer",
        password=SPECIAL_PASSWORD,
        host="postgres",
        port=5432,
        database="customer_platform",
    )
    parsed = make_url(rendered)

    assert parsed.drivername == "postgresql+psycopg"
    assert parsed.username == "customer"
    assert parsed.password == SPECIAL_PASSWORD
    assert parsed.host == "postgres"
    assert parsed.port == 5432
    assert parsed.database == "customer_platform"
    assert SPECIAL_PASSWORD not in rendered
    assert parsed.render_as_string(hide_password=True).count("***") == 1
    assert SPECIAL_PASSWORD not in parsed.render_as_string(hide_password=True)


def test_encoded_password_survives_configparser() -> None:
    rendered = build_database_url(
        username="customer",
        password=SPECIAL_PASSWORD,
        host="postgres",
        port=5432,
        database="customer_platform",
    )
    parser = ConfigParser()
    parser["alembic"] = {"sqlalchemy.url": escape_for_configparser(rendered)}

    assert make_url(parser.get("alembic", "sqlalchemy.url")).password == SPECIAL_PASSWORD


def test_database_url_overrides_compose_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://host_user@localhost:5432/customer_platform",
    )
    monkeypatch.setenv("POSTGRES_USER", "customer")
    monkeypatch.setenv("POSTGRES_PASSWORD", SPECIAL_PASSWORD)
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_DB", "customer_platform")

    settings = Settings(_env_file=None)
    parsed = make_url(settings.database_url or "")

    assert parsed.host == "localhost"
    assert parsed.username == "host_user"
    assert parsed.password is None
    assert SPECIAL_PASSWORD not in (settings.database_url or "")


def test_compose_fields_build_a_url_when_database_url_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "customer")
    monkeypatch.setenv("POSTGRES_PASSWORD", SPECIAL_PASSWORD)
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "customer_platform")

    settings = Settings(_env_file=None)
    parsed = make_url(settings.database_url or "")

    assert parsed.host == "postgres"
    assert parsed.password == SPECIAL_PASSWORD
    assert SPECIAL_PASSWORD not in (settings.database_url or "")


def test_configuration_error_does_not_include_the_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    monkeypatch.delenv("POSTGRES_DB", raising=False)
    monkeypatch.setenv("POSTGRES_PASSWORD", SPECIAL_PASSWORD)

    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None)

    assert SPECIAL_PASSWORD not in str(caught.value)
