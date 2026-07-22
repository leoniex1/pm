import json

import pytest
from fastapi.testclient import TestClient

from backend.app.board_store import reset_database
from backend.app.main import app
from backend.app.openrouter_service import OpenRouterReply


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


def _board(client: TestClient) -> dict:
    response = client.get("/api/board")
    assert response.status_code == 200
    return response.json()


def _mock_structured_response(monkeypatch: pytest.MonkeyPatch, payload: dict) -> None:
    response_text = json.dumps(payload)

    def _fake_query_openrouter(_: str) -> OpenRouterReply:
        return OpenRouterReply(model="openai/gpt-oss-120b", text=response_text)

    monkeypatch.setattr("backend.app.main.query_openrouter", _fake_query_openrouter)


def test_valid_structured_response_applies_operations(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Done.",
            "operations": [
                {
                    "id": "op-1",
                    "type": "rename_column",
                    "column_id": "col-backlog",
                    "title": "Planned",
                },
                {
                    "id": "op-2",
                    "type": "create_card",
                    "card_id": "card-ai-1",
                    "column_id": "col-backlog",
                    "title": "AI created",
                    "details": "Created by AI",
                    "position": 0,
                },
            ],
        },
    )

    response = client.post(
        "/api/ai/respond",
        json={"message": "please update board", "history": []},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["assistant_message"] == "Done."
    assert payload["operations"][0]["id"] == "op-1"

    board = _board(client)
    assert board["columns"][0]["title"] == "Planned"
    assert board["columns"][0]["cardIds"][0] == "card-ai-1"


def test_incomplete_create_card_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Created card.",
            "operations": [
                {
                    "id": "op-1",
                    "type": "create_card",
                }
            ],
        },
    )

    response = client.post("/api/ai/respond", json={"message": "create", "history": []})
    assert response.status_code == 422
    assert "create_card" in response.json()["detail"]


def test_complete_create_card_is_applied(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Created card.",
            "operations": [
                {
                    "id": "op-create-1",
                    "type": "create_card",
                    "card_id": "ai-card-abc123",
                    "column_id": "col-backlog",
                    "title": "Review budget",
                    "details": "Review next quarter budget.",
                    "position": 0,
                }
            ],
        },
    )

    response = client.post("/api/ai/respond", json={"message": "create", "history": []})
    assert response.status_code == 200

    board = _board(client)
    assert board["columns"][0]["cardIds"][0] == "ai-card-abc123"


def test_incomplete_rename_column_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Renamed column.",
            "operations": [
                {
                    "id": "op-1",
                    "type": "rename_column",
                }
            ],
        },
    )

    response = client.post("/api/ai/respond", json={"message": "rename", "history": []})
    assert response.status_code == 422
    assert "rename_column" in response.json()["detail"]


def test_complete_rename_column_is_applied(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Renamed column.",
            "operations": [
                {
                    "id": "op-rename-1",
                    "type": "rename_column",
                    "column_id": "col-review",
                    "title": "Quality Check",
                }
            ],
        },
    )

    response = client.post("/api/ai/respond", json={"message": "rename", "history": []})
    assert response.status_code == 200

    board = _board(client)
    titles = {column["id"]: column["title"] for column in board["columns"]}
    assert titles["col-review"] == "Quality Check"


def test_invalid_json_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    def _fake_query_openrouter(_: str) -> OpenRouterReply:
        return OpenRouterReply(model="openai/gpt-oss-120b", text="not-json")

    monkeypatch.setattr("backend.app.main.query_openrouter", _fake_query_openrouter)

    response = client.post("/api/ai/respond", json={"message": "hi", "history": []})
    assert response.status_code == 422
    assert "not valid JSON" in response.json()["detail"]


def test_chat_only_response_with_no_operations_is_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)

    before = _board(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Here is your summary.",
            "operations": [],
        },
    )

    response = client.post("/api/ai/respond", json={"message": "summarize", "history": []})
    assert response.status_code == 200
    assert response.json()["operations"] == []

    after = _board(client)
    assert after == before


def test_unknown_operation_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Done.",
            "operations": [{"id": "op-1", "type": "archive_card", "card_id": "card-1"}],
        },
    )

    response = client.post("/api/ai/respond", json={"message": "archive", "history": []})
    assert response.status_code == 422


def test_unknown_fields_are_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Done.",
            "operations": [
                {
                    "id": "op-1",
                    "type": "update_card",
                    "card_id": "card-1",
                    "title": "Updated",
                    "extra": "forbidden",
                }
            ],
        },
    )

    response = client.post("/api/ai/respond", json={"message": "update", "history": []})
    assert response.status_code == 422


def test_duplicate_operation_ids_are_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Done.",
            "operations": [
                {"id": "op-dup", "type": "rename_column", "column_id": "col-backlog", "title": "One"},
                {"id": "op-dup", "type": "rename_column", "column_id": "col-review", "title": "Two"},
            ],
        },
    )

    response = client.post("/api/ai/respond", json={"message": "rename", "history": []})
    assert response.status_code == 422
    assert "Duplicate operation id" in response.json()["detail"]


def test_duplicate_create_card_ids_are_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Done.",
            "operations": [
                {
                    "id": "op-1",
                    "type": "create_card",
                    "card_id": "card-ai-dupe",
                    "column_id": "col-backlog",
                    "title": "A",
                    "details": "A",
                    "position": 0,
                },
                {
                    "id": "op-2",
                    "type": "create_card",
                    "card_id": "card-ai-dupe",
                    "column_id": "col-backlog",
                    "title": "B",
                    "details": "B",
                    "position": 1,
                },
            ],
        },
    )

    response = client.post("/api/ai/respond", json={"message": "create", "history": []})
    assert response.status_code == 422
    assert "Duplicate create_card id" in response.json()["detail"]


def test_invalid_position_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Done.",
            "operations": [
                {
                    "id": "op-1",
                    "type": "move_card",
                    "card_id": "card-1",
                    "column_id": "col-done",
                    "position": 99,
                }
            ],
        },
    )

    response = client.post("/api/ai/respond", json={"message": "move", "history": []})
    assert response.status_code == 422
    assert "Invalid position" in response.json()["detail"]


def test_cross_board_reference_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Done.",
            "operations": [
                {
                    "id": "op-1",
                    "type": "delete_card",
                    "card_id": "foreign-user-card",
                }
            ],
        },
    )

    response = client.post("/api/ai/respond", json={"message": "delete", "history": []})
    assert response.status_code == 422
    assert "cross-board" in response.json()["detail"]


def test_validate_entire_operations_before_apply_anything(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    before = _board(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Done.",
            "operations": [
                {"id": "op-1", "type": "rename_column", "column_id": "col-backlog", "title": "Renamed"},
                {
                    "id": "op-2",
                    "type": "move_card",
                    "card_id": "card-1",
                    "column_id": "col-done",
                    "position": 999,
                },
            ],
        },
    )

    response = client.post("/api/ai/respond", json={"message": "mixed", "history": []})
    assert response.status_code == 422

    after = _board(client)
    assert after["columns"][0]["title"] == before["columns"][0]["title"]


def test_transaction_rollback_when_execution_fails(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)
    before = _board(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Done.",
            "operations": [
                {"id": "op-1", "type": "rename_column", "column_id": "col-backlog", "title": "Renamed"}
            ],
        },
    )

    def _raise_save_board(*args, **kwargs):
        raise RuntimeError("db write failed")

    monkeypatch.setattr("backend.app.main.save_board", _raise_save_board)

    response = client.post("/api/ai/respond", json={"message": "rename", "history": []})
    assert response.status_code == 500

    after = _board(client)
    assert after["columns"][0]["title"] == before["columns"][0]["title"]


def test_successful_commit_persists_changes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "Done.",
            "operations": [
                {"id": "op-1", "type": "rename_column", "column_id": "col-review", "title": "QA"}
            ],
        },
    )

    response = client.post("/api/ai/respond", json={"message": "rename review", "history": []})
    assert response.status_code == 200

    after = _board(client)
    titles = {column["id"]: column["title"] for column in after["columns"]}
    assert titles["col-review"] == "QA"


def test_nonexistent_entity_chat_only_noop_returns_200_and_no_mutation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    before = _board(client)

    _mock_structured_response(
        monkeypatch,
        {
            "assistant_message": "I could not find that card or column, so I did not apply changes.",
            "operations": [],
        },
    )

    response = client.post("/api/ai/respond", json={"message": "move a nonexistent card", "history": []})
    assert response.status_code == 200
    assert response.json()["operations"] == []

    after = _board(client)
    assert after == before


def test_empty_message_is_rejected(client: TestClient) -> None:
    _login(client)
    response = client.post("/api/ai/respond", json={"message": "", "history": []})
    assert response.status_code == 422


def test_overlong_message_is_rejected(client: TestClient) -> None:
    _login(client)
    response = client.post("/api/ai/respond", json={"message": "x" * 4001, "history": []})
    assert response.status_code == 422


def test_ai_respond_is_rate_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)
    monkeypatch.setattr("backend.app.main._AI_RATE_LIMIT_MAX_REQUESTS", 2)

    _mock_structured_response(
        monkeypatch,
        {"assistant_message": "Here is your summary.", "operations": []},
    )

    first = client.post("/api/ai/respond", json={"message": "summarize", "history": []})
    second = client.post("/api/ai/respond", json={"message": "summarize", "history": []})
    third = client.post("/api/ai/respond", json={"message": "summarize", "history": []})

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
