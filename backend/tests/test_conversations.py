import os
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

os.environ["STEPWISE_DATABASE_URL"] = f"sqlite:///./test_conversations_{uuid.uuid4().hex}.db"

import database as database_module
from database import SessionLocal, create_tables
from main import app
from models import Message

client = TestClient(app)


def test_create_conversation_and_store_chat_history():
    email = f"student2-{uuid.uuid4().hex[:8]}@example.com"
    register_response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Student Two",
            "password": "securepass123",
        },
    )
    assert register_response.status_code == 200

    login_response = client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": "securepass123",
        },
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    create_response = client.post(
        "/api/conversations",
        json={"title": "Algorithms Practice", "subject": "Algorithms"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_response.status_code == 200
    conversation = create_response.json()
    assert conversation["title"] == "Algorithms Practice"
    assert conversation["subject"] == "Algorithms"
    conversation_id = conversation["id"]

    chat_response = client.post(
        "/api/chat",
        json={
            "message": "How do I reason about loop invariants?",
            "subject": "Algorithms",
            "conversation_id": conversation_id,
            "history": [{"role": "user", "text": "What is a loop invariant?"}],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert chat_response.status_code == 200
    assert "reply" in chat_response.json()

    history_response = client.get(
        f"/api/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history_response.status_code == 200
    payload = history_response.json()
    assert payload["title"] == "Algorithms Practice"
    assert payload["subject"] == "Algorithms"
    assert len(payload["messages"]) >= 2

    list_response = client.get(
        "/api/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["subject"] == "Algorithms"

    mismatched_chat_response = client.post(
        "/api/chat",
        json={
            "message": "How does a TCP handshake work?",
            "subject": "Networking",
            "conversation_id": conversation_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert mismatched_chat_response.status_code == 409


def test_existing_conversations_migrate_to_uncategorized(monkeypatch):
    legacy_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with legacy_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE conversations ("
                "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title VARCHAR NOT NULL, "
                "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO conversations (id, user_id, title, created_at, updated_at) "
                "VALUES (1, 1, 'Older chat', '2026-01-01', '2026-01-01')"
            )
        )

    monkeypatch.setattr(database_module, "engine", legacy_engine)
    create_tables()

    with legacy_engine.connect() as connection:
        subject = connection.execute(
            text("SELECT subject FROM conversations WHERE id = 1")
        ).scalar_one()

    assert subject == "Uncategorized"
    legacy_engine.dispose()


def test_default_conversation_title_comes_from_first_message(monkeypatch):
    monkeypatch.setattr(
        "main.generate_socratic_response",
        lambda **kwargs: "What entities and relationships do you notice?",
    )
    email = f"title-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "securepass123"},
    )
    login_response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "securepass123"},
    )
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}
    conversation = client.post(
        "/api/conversations",
        json={"subject": "Software Engineering"},
        headers=headers,
    ).json()

    chat_response = client.post(
        "/api/chat",
        json={
            "message": "  What is ER modelling in software engineering?  ",
            "subject": "Software Engineering",
            "conversation_id": conversation["id"],
        },
        headers=headers,
    )

    assert chat_response.status_code == 200
    detail = client.get(f"/api/conversations/{conversation['id']}", headers=headers).json()
    assert detail["title"] == "What is ER modelling in software engineering?"


def test_history_list_backfills_default_titles_from_saved_messages():
    email = f"backfill-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "securepass123"},
    )
    login_response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "securepass123"},
    )
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}
    conversation = client.post(
        "/api/conversations",
        json={"subject": "Algorithms"},
        headers=headers,
    ).json()

    db = SessionLocal()
    try:
        db.add(
            Message(
                conversation_id=conversation["id"],
                role="user",
                content="How does binary search narrow the range?",
            )
        )
        db.commit()
    finally:
        db.close()

    list_response = client.get("/api/conversations", headers=headers)

    assert list_response.status_code == 200
    titled_chat = next(item for item in list_response.json() if item["id"] == conversation["id"])
    assert titled_chat["title"] == "How does binary search narrow the range?"


def test_history_list_hides_empty_conversation_drafts():
    email = f"empty-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "securepass123"},
    )
    login_response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "securepass123"},
    )
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}
    empty_conversation = client.post(
        "/api/conversations",
        json={"subject": "Networking"},
        headers=headers,
    ).json()

    list_response = client.get("/api/conversations", headers=headers)

    assert list_response.status_code == 200
    assert all(item["id"] != empty_conversation["id"] for item in list_response.json())
