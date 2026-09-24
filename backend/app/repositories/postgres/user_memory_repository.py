"""PostgreSQL persistence for durable user memory."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import models as db
from app.db.session import SessionFactory
from app.repositories.interfaces import UserMemoryRepository
from app.services.chat_domain import UserMemory


class PostgresUserMemoryRepository(UserMemoryRepository):
    """Store and retrieve memories with an owner and key scope."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def list_memories(self, owner_id: str) -> list[UserMemory]:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(db.UserMemoryRecord)
                    .where(db.UserMemoryRecord.user_id == owner_id)
                    .order_by(db.UserMemoryRecord.updated_at.desc())
                )
                .scalars()
                .all()
            )
        return [self._to_domain(row) for row in rows]

    def upsert_memory(self, owner_id: str, key: str, value: str) -> UserMemory:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            row = session.scalar(
                select(db.UserMemoryRecord).where(
                    db.UserMemoryRecord.user_id == owner_id,
                    db.UserMemoryRecord.memory_key == key,
                )
            )
            if row is None:
                row = db.UserMemoryRecord(
                    id=str(uuid.uuid4()),
                    user_id=owner_id,
                    memory_key=key,
                    memory_value=value,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.memory_value = value
                row.updated_at = now
            try:
                session.commit()
            except Exception:
                session.rollback()
                raise
            session.refresh(row)
            return self._to_domain(row)

    @staticmethod
    def _to_domain(row: db.UserMemoryRecord) -> UserMemory:
        return UserMemory(
            memory_id=row.id,
            owner_id=row.user_id,
            key=row.memory_key,
            value=row.memory_value,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )