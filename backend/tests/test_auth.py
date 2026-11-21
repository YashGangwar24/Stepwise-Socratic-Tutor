import os
import uuid

from fastapi.testclient import TestClient

os.environ["STEPWISE_DATABASE_URL"] = f"sqlite:///./test_auth_{uuid.uuid4().hex}.db"

from database import create_tables
from main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "StepWise Backend is running!"


def test_register_and_login_flow():
    email = f"student-{uuid.uuid4().hex[:8]}@example.com"
    password = "securepass123"

    register_response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Student User",
            "password": password,
            "role": "student",
        },
    )
    assert register_response.status_code == 200
    user = register_response.json()
    assert user["email"] == email
    assert user["full_name"] == "Student User"
    assert user["role"] == "student"

    login_response = client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert login_response.status_code == 200
    payload = login_response.json()
    assert "access_token" in payload
    assert payload["token_type"] == "bearer"

    me_response = client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == email
    assert me_response.json()["role"] == "student"


def test_invalid_role_is_rejected():
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"bad-role-{uuid.uuid4().hex[:8]}@example.com",
            "full_name": "Bad Role",
            "password": "securepass123",
            "role": "admin",
        },
    )
    assert response.status_code == 400
    assert "role" in response.json()["detail"].lower()


def test_registration_rejects_malformed_email_and_short_password():
    bad_email = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "securepass123"},
    )
    short_password = client.post(
        "/api/auth/register",
        json={"email": f"short-{uuid.uuid4().hex[:8]}@example.com", "password": "short"},
    )
    assert bad_email.status_code == 422
    assert short_password.status_code == 422


def test_password_reset_requires_email_token_and_invalidates_it(monkeypatch):
    email = f"reset-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "securepass123"},
    )
    old_login_token = client.post(
        "/api/auth/login",
        json={"email": email, "password": "securepass123"},
    ).json()["access_token"]
    reset_email = {}
    monkeypatch.setattr("main.password_reset_email_configured", lambda: True)
    monkeypatch.setattr(
        "main.send_password_reset_email",
        lambda recipient, reset_url: reset_email.update(recipient=recipient, url=reset_url),
    )

    request_response = client.post(
        "/api/auth/password-reset/request",
        json={"email": email},
    )
    assert request_response.status_code == 200
    assert "If an account exists" in request_response.json()["message"]
    assert reset_email["recipient"] == email
    unknown_email_response = client.post(
        "/api/auth/password-reset/request",
        json={"email": "unknown@example.com"},
    )
    assert unknown_email_response.json() == request_response.json()

    from urllib.parse import parse_qs, urlparse

    reset_token = parse_qs(urlparse(reset_email["url"]).query)["reset_token"][0]
    reset_response = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "a-new-secure-password"},
    )
    assert reset_response.status_code == 200

    replay_response = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "another-secure-password"},
    )
    assert replay_response.status_code == 400

    old_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "securepass123"},
    )
    new_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "a-new-secure-password"},
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200
    old_session = client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {old_login_token}"},
    )
    assert old_session.status_code == 401


def test_password_reset_request_requires_email_configuration(monkeypatch):
    monkeypatch.setattr("main.password_reset_email_configured", lambda: False)
    response = client.post(
        "/api/auth/password-reset/request",
        json={"email": "someone@example.com"},
    )
    assert response.status_code == 503


def test_local_password_reset_works_without_smtp(monkeypatch):
    monkeypatch.setattr("main.password_reset_email_configured", lambda: False)
    email = f"local-reset-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "securepass123"},
    )
    local_client = TestClient(
        app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )

    reset_request = local_client.post(
        "/api/auth/password-reset/request",
        json={"email": email},
    )

    assert reset_request.status_code == 200
    reset_url = reset_request.json()["reset_url"]
    assert "reset_token=" in reset_url
    token = reset_url.split("reset_token=", 1)[1]
    assert local_client.get(
        "/api/users/me", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 401
    reset_response = local_client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "new_password": "new-secure-password"},
    )
    assert reset_response.status_code == 200
    assert client.post(
        "/api/auth/login",
        json={"email": email, "password": "new-secure-password"},
    ).status_code == 200


def test_instructor_can_manage_syllabus_mapping(monkeypatch):
    monkeypatch.setenv("STEPWISE_FACULTY_INVITE_CODE", "test-faculty-invite")
    email = f"faculty-{uuid.uuid4().hex[:8]}@example.com"
    register_response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Instructor User",
            "password": "securepass123",
            "role": "faculty",
            "faculty_invite_code": "test-faculty-invite",
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
    token = login_response.json()["access_token"]

    create_mapping = client.post(
        "/api/syllabus/mappings",
        json={
            "subject": "Algorithms",
            "module": "Module 3",
            "chapter": "Recursion",
            "persona": "Focus on recursion trees and proof by induction.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_mapping.status_code == 200
    payload = create_mapping.json()
    assert payload["subject"] == "Algorithms"
    assert payload["module"] == "Module 3"
    assert payload["chapter"] == "Recursion"

    list_mapping = client.get(
        "/api/syllabus/mappings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_mapping.status_code == 200
    assert any(item["subject"] == "Algorithms" for item in list_mapping.json())


def test_faculty_registration_requires_invitation(monkeypatch):
    monkeypatch.delenv("STEPWISE_FACULTY_INVITE_CODE", raising=False)
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"uninvited-{uuid.uuid4().hex[:8]}@example.com",
            "password": "securepass123",
            "role": "faculty",
        },
    )
    assert response.status_code == 403
