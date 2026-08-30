"""API-level tests for the conversation history endpoints.

Uses an isolated ``ConversationsService`` bound to an in-memory JSON store and
overrides the authentication dependency so no JWT/signing secret is required.
These tests verify the HTTP contract: create, list, get, messages, rename,
delete, and that cross-owner access is rejected with 404 for a given
conversation.
"""

from fastapi.testclient import TestClient

from app.api.dependencies import get_conversations_service, get_current_user
from app.main import app
from app.services.auth import User
from app.services.chat_domain import ConversationMeta
from app.services.chat.conversations_service import ConversationsService
from app.services.chat.memory import ConversationMemory

ALICE = User(
    user_id="user-alice",
    email="alice@example.com",
    password_hash="hashed",
    is_active=True,
)
BOB = User(
    user_id="user-bob",
    email="bob@example.com",
    password_hash="hashed",
    is_active=True,
)


def _make_client(owner: User, service: ConversationsService) -> TestClient:
    """Build a TestClient with auth and service overrides for a user.

    Args:
        owner: The user to resolve as the authenticated caller.
        service: The ConversationsService to inject.

    Returns:
        A configured TestClient.
    """

    def _override_user():
        return owner

    def _override_service():
        return service

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_conversations_service] = _override_service
    return TestClient(app)


def _cleanup(client: TestClient) -> None:
    """Remove dependency overrides after a test."""
    app.dependency_overrides.clear()
    client.close()


def test_full_conversation_lifecycle() -> None:
    service = ConversationsService(ConversationMemory(None))
    client = _make_client(ALICE, service)
    try:
        created = client.post("/conversations")
        assert created.status_code == 201
        data = created.json()["data"]
        conversation_id = data["conversation_id"]
        assert data["title"] is None

        listed = client.get("/conversations")
        assert listed.status_code == 200
        assert [m["conversation_id"] for m in listed.json()["data"]] == [
            conversation_id
        ]

        got = client.get(f"/conversations/{conversation_id}")
        assert got.status_code == 200
        assert got.json()["data"]["conversation_id"] == conversation_id

        messages = client.get(f"/conversations/{conversation_id}/messages")
        assert messages.status_code == 200
        assert messages.json()["data"] == []

        renamed = client.patch(
            f"/conversations/{conversation_id}", json={"title": "My chat"}
        )
        assert renamed.status_code == 200
        assert renamed.json()["data"]["title"] == "My chat"

        deleted = client.delete(f"/conversations/{conversation_id}")
        assert deleted.status_code == 200
        assert deleted.json()["data"]["status"] == "deleted"

        assert client.get(f"/conversations/{conversation_id}").status_code == 404
    finally:
        _cleanup(client)


def test_cross_owner_operations_rejected_with_404() -> None:
    service = ConversationsService(ConversationMemory(None))
    meta: ConversationMeta = service.create(ALICE.user_id)

    bob_client = _make_client(BOB, service)
    try:
        assert bob_client.get(f"/conversations/{meta.conversation_id}").status_code == 404
        assert (
            bob_client.get(f"/conversations/{meta.conversation_id}/messages").status_code
            == 404
        )
        assert (
            bob_client.patch(
                f"/conversations/{meta.conversation_id}", json={"title": "mine"}
            ).status_code
            == 404
        )
        assert (
            bob_client.delete(f"/conversations/{meta.conversation_id}").status_code
            == 404
        )
    finally:
        _cleanup(bob_client)

    # Alice's conversation is untouched and still owned by her.
    alice_client = _make_client(ALICE, service)
    try:
        assert (
            alice_client.get(f"/conversations/{meta.conversation_id}").json()["data"][
                "title"
            ]
            is None
        )
    finally:
        _cleanup(alice_client)


def test_list_and_get_scoped_per_user() -> None:
    service = ConversationsService(ConversationMemory(None))
    service.create(ALICE.user_id)
    service.create(BOB.user_id)

    alice_client = _make_client(ALICE, service)
    try:
        alice_ids = [
            m["conversation_id"] for m in alice_client.get("/conversations").json()["data"]
        ]
        assert len(alice_ids) == 1
    finally:
        _cleanup(alice_client)

    bob_client = _make_client(BOB, service)
    try:
        bob_ids = [
            m["conversation_id"] for m in bob_client.get("/conversations").json()["data"]
        ]
        assert len(bob_ids) == 1
        assert alice_ids != bob_ids
    finally:
        _cleanup(bob_client)
