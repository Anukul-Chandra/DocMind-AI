"""PostgreSQL-backed implementation of the UserRepository abstraction."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import models as db
from app.db.session import SessionFactory
from app.services.auth.auth_service import User, UserRepository


class PostgresUserRepository(UserRepository):
    """PostgreSQL user repository.

    Maps the ``users`` table to the domain :class:`User` model. Email
    uniqueness is enforced by the database-level unique constraint; a
    duplicate create is surfaced as a :class:`ValueError` so the upcoming
    registration flow can react without touching SQLAlchemy.
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        """Initialize the repository with a session factory.

        Args:
            session_factory: A callable returning a fresh session per
                operation.
        """
        self._session_factory = session_factory

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
            ValueError: If the email is already in use.
        """
        user_id = user_id or str(uuid.uuid4())
        with self._session_factory() as session:
            session.add(
                db.User(
                    id=user_id,
                    email=email,
                    password_hash=password_hash,
                    is_active=is_active,
                )
            )
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError(
                    f"A user with email {email!r} already exists."
                ) from exc
        return User(
            user_id=user_id,
            email=email,
            password_hash=password_hash,
            is_active=is_active,
        )

    def get_by_email(self, email: str) -> User | None:
        """Return the user with the given email, or None.

        Args:
            email: The email address to look up.

        Returns:
            The matching user, or None if the email is unknown.
        """
        with self._session_factory() as session:
            row = session.scalar(
                select(db.User).where(db.User.email == email)
            )
        return self._to_domain(row) if row is not None else None

    def get_by_id(self, user_id: str) -> User | None:
        """Return the user with the given id, or None.

        Args:
            user_id: The user identifier to look up.

        Returns:
            The matching user, or None if the id is unknown.
        """
        with self._session_factory() as session:
            row = session.get(db.User, user_id)
        return self._to_domain(row) if row is not None else None

    @staticmethod
    def _to_domain(row: db.User) -> User:
        """Convert a user row to the domain model.

        Args:
            row: The database user row.

        Returns:
            The domain :class:`User`.
        """
        return User(
            user_id=row.id,
            email=row.email,
            password_hash=row.password_hash,
            is_active=row.is_active,
        )