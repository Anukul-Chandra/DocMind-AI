"""PostgreSQL conversation repository regression test.

Verifies the transaction fix for :class:`PostgresConversationRepository`:
writes are committed, so a fresh session (as created for every subsequent
repository operation) observes the persisted conversation and messages.

The repository is exercised through a real SQLAlchemy session factory. The
schema is created on a temporary SQLite database by default so the test runs
even when PostgreSQL is unreachable; the exact same code paths run against
PostgreSQL unchanged.

Usage (from backend/):
    python -m app.scripts.test_conversation_repository_postgres

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import models as db  # noqa: F401  (register tables on Base.metadata)
from app.db.base import Base
from app.repositories.postgres.conversation_repository import (
    PostgresConversationRepository,
)


def main() -> int:
    """Run the conversation repository regression test."""
    print("=" * 60)
    print("PostgreSQL Conversation Repository Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "conversations.db"
        url = f"sqlite:///{db_path.as_posix()}"
        engine = create_engine(url)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        Base.metadata.create_all(engine)

        repository = PostgresConversationRepository(session_factory)

        # A created conversation persists across sessions.
        conversation_id = repository.create_conversation()
        with session_factory() as session:
            row = session.get(db.Conversation, conversation_id)
        check(
            "created conversation persists in a fresh session",
            row is not None,
            conversation_id,
        )
        check(
            "new conversation has empty history",
            repository.get_history(conversation_id) == [],
        )

        # An exchange persists: conversation row and both chat messages.
        repository.add_exchange(conversation_id, "hello", "hi there")
        with session_factory() as session:
            messages = (
                session.execute(
                    select(db.ChatMessage).where(
                        db.ChatMessage.conversation_id == conversation_id
                    )
                )
                .scalars()
                .all()
            )
        check(
            "exchange persists in a fresh session",
            [(m.role, m.content) for m in messages]
            == [("user", "hello"), ("assistant", "hi there")],
        )
        check(
            "history reflects the stored exchange",
            repository.get_history(conversation_id)
            == [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
        )

        # add_exchange implicitly creates an unknown conversation and persists.
        other_id = "implicit-conversation"
        repository.add_exchange(other_id, "q", "a")
        with session_factory() as session:
            conversation = session.get(db.Conversation, other_id)
            messages = session.scalars(
                select(db.ChatMessage).where(
                    db.ChatMessage.conversation_id == other_id
                )
            ).all()
        check(
            "add_exchange auto-creates and persists the conversation",
            conversation is not None and len(messages) == 2,
        )

        engine.dispose()

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print(
        "Conversation Repository Test "
        + ("PASSED" if all_passed else "FAILED")
    )
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
