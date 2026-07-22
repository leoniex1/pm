import pytest
from fastapi.testclient import TestClient

from backend.app.board_store import (
    SessionLocal,
    User,
    _hash_password,
    _verify_password,
    authenticate_user,
    reset_database,
)
from backend.app.main import app


@pytest.fixture(autouse=True)
def reset_db() -> None:
    reset_database()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_password_is_hashed_not_plaintext_at_rest() -> None:
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "user").one()
        assert user.password_hash != "password"
        assert user.password_hash.startswith("$2b$")


def test_hash_and_verify_round_trip() -> None:
    hashed = _hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert _verify_password("correct horse battery staple", hashed) is True
    assert _verify_password("wrong password", hashed) is False


def test_authenticate_user_accepts_correct_password_via_hash_verification() -> None:
    with SessionLocal() as session:
        user = authenticate_user(session, "user", "password")
        assert user is not None
        assert user.username == "user"


def test_authenticate_user_rejects_incorrect_password() -> None:
    with SessionLocal() as session:
        user = authenticate_user(session, "user", "not-the-password")
        assert user is None


def test_login_endpoint_still_works_end_to_end_with_hashed_storage(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "password"},
    )
    assert response.status_code == 200
    assert response.json()["authenticated"] is True
