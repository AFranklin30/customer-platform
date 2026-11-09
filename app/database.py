"""SQLAlchemy engine and session factory.

Customer creation commits inside the service. The session dependency only
opens and closes a session. Closing a session rolls back a transaction that
was left open by an error, which keeps a failed request from being committed
by accident.
"""

from __future__ import annotations

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

# Check constraints are named explicitly on the models. A "ck" convention that
# includes %(constraint_name)s would rewrite those explicit names.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ix": "ix_%(column_0_label)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


settings = get_settings()
database_url = settings.database_url
if database_url is None:
    raise RuntimeError("Database configuration is incomplete.")
engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args={"options": "-c timezone=UTC"},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
