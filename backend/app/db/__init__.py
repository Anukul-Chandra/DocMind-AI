"""Database layer for the PostgreSQL persistence backend."""

from app.db.base import Base
from app.db import models  # noqa: F401  (register tables on Base.metadata)

__all__ = ["Base"]
