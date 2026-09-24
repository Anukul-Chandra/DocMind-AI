"""JSON-backed persistence for durable user memory."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.repositories.interfaces import UserMemoryRepository
from app.services.chat_domain import UserMemory
from app.services.storage import JsonFileStore


class JsonUserMemoryRepository(UserMemoryRepository):
    """Persist explicit user facts without sharing them across owners."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._memories: dict[tuple[str, str], dict] = {}
        self._load()

    def list_memories(self, owner_id: str) -> list[UserMemory]:
        rows = [
            self._to_domain(record)
            for (record_owner, _), record in self._memories.items()
            if record_owner == owner_id
        ]
        return sorted(rows, key=lambda memory: memory.updated_at, reverse=True)

    def upsert_memory(self, owner_id: str, key: str, value: str) -> UserMemory:
        now = datetime.now(timezone.utc).isoformat()
        identity = (owner_id, key)
        record = self._memories.get(identity)
        if record is None:
            record = {
                "id": str(uuid.uuid4()),
                "owner_id": owner_id,
                "key": key,
                "value": value,
                "created_at": now,
            }
            self._memories[identity] = record
        else:
            record["value"] = value
        record["updated_at"] = now
        self._save()
        return self._to_domain(record)

    def _load(self) -> None:
        for item in JsonFileStore.load(self._path, default=[]):
            owner_id = item.get("owner_id")
            key = item.get("key")
            if owner_id and key and item.get("id") and item.get("value") is not None:
                self._memories[(owner_id, key)] = item

    def _save(self) -> None:
        JsonFileStore.save(self._path, list(self._memories.values()))

    @staticmethod
    def _to_domain(record: dict) -> UserMemory:
        return UserMemory(
            memory_id=record["id"],
            owner_id=record["owner_id"],
            key=record["key"],
            value=record["value"],
            created_at=_parse_datetime(record["created_at"]),
            updated_at=_parse_datetime(record["updated_at"]),
        )


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)