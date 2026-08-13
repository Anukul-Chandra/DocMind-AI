"""JSON-backed implementation of the UserRepository abstraction."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.services.auth.auth_service import User, UserRepository
from app.services.storage import JsonFileStore


class JsonUserRepository(UserRepository):
    """JSON user repository.

    Persists users to a single JSON file using :class:`JsonFileStore`, which
    automatically creates missing parent directories and returns an empty list
    for absent files. Records retain the full user state (including
    ``created_at`` and ``updated_at``) so the store survives reloads; the
    domain :class:`User` is re-derived from each record on retrieval.
    """

    def __init__(self, path: str | Path) -> None:
        """Initialize the repository and load any existing users.

        Args:
            path: Filesystem path to the JSON storage file.
        """
        self._path = Path(path)
        self._records: dict[str, dict] = {}
        self._load()

    def create(
        self,
        email: str,
        password_hash: str,
        user_id: str | None = None,
        is_active: bool = True,
    ) -> User:
        """Create a new user and persist it.

        Args:
            email: The user's unique email address.
            password_hash: The pre-hashed password. Plaintext passwords must
                never be passed here.
            user_id: An explicit identifier, or None to generate one.
            is_active: Whether the new account should be active.

        Returns:
            The created user.

        Raises:
            ValueError: If the email (or explicit id) is already in use.
        """
        if self.get_by_email(email) is not None:
            raise ValueError(f"A user with email {email!r} already exists.")
        user_id = user_id or str(uuid.uuid4())
        if user_id in self._records:
            raise ValueError(f"A user with id {user_id!r} already exists.")
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": user_id,
            "email": email,
            "password_hash": password_hash,
            "created_at": now,
            "updated_at": now,
            "is_active": is_active,
        }
        self._records[user_id] = record
        self._save()
        return self._to_domain(record)

    def get_by_email(self, email: str) -> User | None:
        """Return the user with the given email, or None.

        Args:
            email: The email address to look up.

        Returns:
            The matching user, or None if the email is unknown.
        """
        for record in self._records.values():
            if record["email"] == email:
                return self._to_domain(record)
        return None

    def get_by_id(self, user_id: str) -> User | None:
        """Return the user with the given id, or None.

        Args:
            user_id: The user identifier to look up.

        Returns:
            The matching user, or None if the id is unknown.
        """
        record = self._records.get(user_id)
        return self._to_domain(record) if record is not None else None

    def _save(self) -> None:
        """Persist the in-memory records to the JSON storage file."""
        JsonFileStore.save(self._path, list(self._records.values()))

    def _load(self) -> None:
        """Load records from the JSON storage file, starting empty if missing."""
        data = JsonFileStore.load(self._path, default=[])
        for item in data:
            record = {
                "id": item["id"],
                "email": item["email"],
                "password_hash": item["password_hash"],
                "created_at": item.get("created_at")
                or datetime.now(timezone.utc).isoformat(),
                "updated_at": item.get("updated_at")
                or datetime.now(timezone.utc).isoformat(),
                "is_active": item.get("is_active", True),
            }
            self._records[record["id"]] = record

    @staticmethod
    def _to_domain(record: dict) -> User:
        """Convert a persisted record to the domain model.

        Args:
            record: The raw stored user record.

        Returns:
            The domain :class:`User`.
        """
        return User(
            user_id=record["id"],
            email=record["email"],
            password_hash=record["password_hash"],
            is_active=record["is_active"],
        )