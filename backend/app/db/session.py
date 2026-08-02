"""Engine and session factory helpers for the PostgreSQL backend.

The application creates one cached session factory bound to
``settings.database_url`` when the ``postgres`` persistence backend is active.
Repositories receive the factory (a ``sessionmaker``) and open a short-lived
session per operation.
"""

from functools import lru_cache
from typing import Callable

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

SessionFactory = Callable[[], Session]


def build_session_factory(database_url: str) -> SessionFactory:
    """Create a session factory bound to a SQLAlchemy database URL.

    Args:
        database_url: A SQLAlchemy engine URL, e.g.
            ``postgresql+psycopg://user:pass@host:5432/dbname``.

    Returns:
        A callable returning a fresh :class:`Session` per invocation.
    """
    engine: Engine = create_engine(database_url, pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


@lru_cache
def get_session_factory() -> SessionFactory:
    """Return the application session factory for the configured database.

    Raises:
        RuntimeError: If no ``database_url`` is configured. This surfaces only
            when the postgres persistence backend is actually used.
    """
    if not settings.database_url:
        raise RuntimeError(
            "database_url is not configured; set PERSISTENCE_BACKEND=json or "
            "provide DATABASE_URL (e.g. "
            "postgresql+psycopg://user:pass@host:5432/dbname)"
        )
    return build_session_factory(settings.database_url)
