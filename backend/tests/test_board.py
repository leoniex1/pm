import pytest
from fastapi.testclient import TestClient

from backend.app.board_store import INITIAL_BOARD_DATA, reset_database
from backend.app.main import app


@pytest.fixture(autouse=True)
def reset_db() -> None:
    reset_database()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "password"},
    )
    assert response.status_code == 200


def test_seeded_board_available_after_login(client: TestClient) -> None:
    _login(client)
    response = client.get("/api/board")
    assert response.status_code == 200

    board = response.json()
    assert len(board["columns"]) == len(INITIAL_BOARD_DATA.columns)
    assert len(board["cards"]) == len(INITIAL_BOARD_DATA.cards)


def test_board_persistence_for_rename_add_delete_and_move(client: TestClient) -> None:
    _login(client)

    initial_response = client.get("/api/board")
    board = initial_response.json()

    board["columns"][0]["title"] = "Renamed Column"

    new_card = {
        "id": "card-persist-test",
        "title": "Persisted card",
        "details": "Should remain after reload.",
    }
    board["cards"][new_card["id"]] = new_card
    board["columns"][0]["cardIds"].append(new_card["id"])

    deleted_card_id = board["columns"][0]["cardIds"].pop(0)
    board["cards"].pop(deleted_card_id)

    moved_card_id = board["columns"][0]["cardIds"].pop(0)
    board["columns"][1]["cardIds"].insert(0, moved_card_id)

    save_response = client.put("/api/board", json=board)
    assert save_response.status_code == 200

    reload_response = client.get("/api/board")
    assert reload_response.status_code == 200
    persisted = reload_response.json()

    assert persisted["columns"][0]["title"] == "Renamed Column"
    assert new_card["id"] in persisted["columns"][0]["cardIds"]
    assert deleted_card_id not in persisted["cards"]
    assert persisted["columns"][1]["cardIds"][0] == moved_card_id


def test_board_route_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/board")
    assert response.status_code == 401


def test_reset_endpoint_unavailable_in_normal_operation(client: TestClient) -> None:
    _login(client)
    response = client.post("/api/board/reset")
    assert response.status_code == 404


def test_reset_endpoint_available_when_explicitly_enabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    monkeypatch.setenv("ALLOW_TEST_RESET", "1")
    response = client.post("/api/board/reset")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_invalid_board_payload_is_rejected(client: TestClient) -> None:
    _login(client)
    response = client.put("/api/board", json={"columns": []})
    assert response.status_code == 422
