import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_is_public(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_unauthenticated_root_redirects_to_login(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_login_session_logout_flow(client: TestClient) -> None:
    login_response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "password"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["authenticated"] is True

    session_response = client.get("/api/auth/session")
    assert session_response.status_code == 200
    assert session_response.json() == {"authenticated": True, "username": "user"}

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 200
    assert logout_response.json() == {"authenticated": False}

    after_logout_response = client.get("/", follow_redirects=False)
    assert after_logout_response.status_code == 307
    assert after_logout_response.headers["location"] == "/login"


def test_invalid_login_fails(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "wrong"},
    )
    assert response.status_code == 401


def test_protected_api_rejects_unauthenticated_requests(client: TestClient) -> None:
    response = client.post("/api/auth/logout")
    assert response.status_code == 401
