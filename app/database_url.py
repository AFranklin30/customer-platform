"""Build the SQLAlchemy database URL from discrete connection fields.

Passwords are not concatenated into a URL string. SQLAlchemy percent-encodes
username, password, and database name, including characters such as @, :, /,
#, and %.
"""

from __future__ import annotations

from sqlalchemy.engine import URL


def build_database_url(
    *,
    username: str,
    password: str,
    host: str,
    port: int,
    database: str,
) -> str:
    url = URL.create(
        drivername="postgresql+psycopg",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    )
    return url.render_as_string(hide_password=False)


def escape_for_configparser(database_url: str) -> str:
    """Double percent signs so ConfigParser keeps them as literal characters."""

    return database_url.replace("%", "%%")
