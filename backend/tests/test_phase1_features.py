import json
import os
import uuid

from fastapi.testclient import TestClient
from database import SessionLocal
from models import Conversation, Message, User

os.environ["STEPWISE_DATABASE_URL"] = f"sqlite:///./test_phase1_{uuid.uuid4().hex}.db"

from main import app

client = TestClient(app)


def test_stream_chat_returns_sse_headers(monkeypatch):
    captured = {}

    def fake_stream(**kwargs):
        captured.update(kwargs)
        return iter(["Step 1", "Step 2"])

    monkeypatch.setattr(
        "main.generate_socratic_response_stream",
        fake_stream,
    )

    email = f"stream-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "securepass123"},
    )
    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "securepass123"},
    )
    token = login.json()["access_token"]

    response = client.get(
        "/api/chat/stream",
        params={
            "message": "Explain binary search",
            "subject": "Algorithms",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert captured["subject"] == "Algorithms"
    assert set(captured) == {"subject", "message", "history", "syllabus_context", "support_level"}


def test_stream_chat_accepts_long_message_in_post_body(monkeypatch):
    captured = {}

    def fake_stream(**kwargs):
        captured.update(kwargs)
        return iter(["A guiding question?"])

    monkeypatch.setattr("main.generate_socratic_response_stream", fake_stream)
    email = f"stream-post-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={"email": email, "password": "securepass123"})
    token = client.post(
        "/api/auth/login", json={"email": email, "password": "securepass123"}
    ).json()["access_token"]
    long_message = "Attached file contents: " + ("x" * (10_000 - len("Attached file contents: ")))

    response = client.post(
        "/api/chat/stream",
        json={"message": long_message, "subject": "Algorithms"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert captured["message"] == long_message


def test_stream_chat_rejects_messages_over_the_documented_limit():
    email = f"stream-limit-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={"email": email, "password": "securepass123"})
    token = client.post(
        "/api/auth/login", json={"email": email, "password": "securepass123"}
    ).json()["access_token"]
    response = client.post(
        "/api/chat/stream",
        json={"message": "x" * 10_001, "subject": "Algorithms"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_stream_chat_validates_conversation_before_starting_sse():
    email = f"stream-conversation-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={"email": email, "password": "securepass123"})
    token = client.post(
        "/api/auth/login", json={"email": email, "password": "securepass123"}
    ).json()["access_token"]
    response = client.post(
        "/api/chat/stream",
        json={"message": "Continue this branch", "subject": "Algorithms", "conversation_id": 999999},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_stream_failure_is_reported_and_saved_as_a_retryable_reply(monkeypatch):
    def failed_stream(**kwargs):
        raise RuntimeError("Ollama is unavailable")

    monkeypatch.setattr("main.generate_socratic_response_stream", failed_stream)
    email = f"stream-error-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={"email": email, "password": "securepass123"})
    token = client.post(
        "/api/auth/login", json={"email": email, "password": "securepass123"}
    ).json()["access_token"]

    response = client.post(
        "/api/chat/stream",
        json={"message": "Explain a graph traversal", "subject": "Algorithms"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    events = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
    payloads = [json.loads(line) for line in events]
    assert any(item.get("error") for item in payloads)
    completion = next(item for item in payloads if item.get("done"))
    conversation = client.get(
        f"/api/conversations/{completion['conversation_id']}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert conversation["messages"][-1]["role"] == "assistant"
    assert "Ollama is running" in conversation["messages"][-1]["content"]


def test_edit_message_creates_branch_for_regeneration():
    email = f"branch-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "securepass123"},
    )
    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "securepass123"},
    )
    token = login.json()["access_token"]

    conversation = client.post(
        "/api/conversations",
        json={"title": "Branch test", "subject": "Algorithms"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    user_message = client.post(
        "/api/chat",
        json={
            "message": "What is a loop invariant?",
            "subject": "Algorithms",
            "conversation_id": conversation["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    conversation_detail = client.get(
        f"/api/conversations/{conversation['id']}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    original_message = next(item for item in conversation_detail["messages"] if item["role"] == "user")

    edit_response = client.post(
        f"/api/messages/{original_message['id']}/edit",
        json={"content": "What is a loop invariant in simple terms?", "role": "assistant"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert edit_response.status_code == 200
    updated = edit_response.json()
    assert updated["parent_message_id"] == original_message["id"]
    assert updated["content"] == "What is a loop invariant in simple terms?"
    assert updated["role"] == "user"


def test_legacy_flat_conversation_is_migrated_to_a_message_path():
    email = f"legacy-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={"email": email, "password": "securepass123"})
    token = client.post(
        "/api/auth/login", json={"email": email, "password": "securepass123"}
    ).json()["access_token"]
    conversation_data = client.post(
        "/api/conversations",
        json={"title": "Legacy chat", "subject": "Algorithms"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        conversation = db.query(Conversation).filter_by(id=conversation_data["id"]).first()
        first = Message(conversation_id=conversation.id, role="user", content="First question")
        second = Message(conversation_id=conversation.id, role="assistant", content="First hint")
        third = Message(conversation_id=conversation.id, role="user", content="Follow-up")
        db.add_all([first, second, third])
        db.commit()
        ids = [first.id, second.id, third.id]
        assert user is not None
    finally:
        db.close()

    result = client.get(
        f"/api/conversations/{conversation_data['id']}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert [message["parent_message_id"] for message in result["messages"]] == [None, *ids[:-1]]
