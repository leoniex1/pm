from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.board_store import reset_database
from backend.app.main import app
from backend.app.openrouter_service import (
    DEFAULT_OPENROUTER_MODEL,
    OpenRouterConfigurationError,
    OpenRouterReply,
    get_openrouter_config,
)


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


def test_missing_api_key_raises_configuration_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_MODEL=openai/gpt-oss-120b\n", encoding="utf-8")

    with pytest.raises(OpenRouterConfigurationError):
        get_openrouter_config(env_file=env_file)


def test_default_model_is_used_when_not_overridden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=test-key\n", encoding="utf-8")

    config = get_openrouter_config(env_file=env_file)
    assert config.model == DEFAULT_OPENROUTER_MODEL


def test_openrouter_model_override_from_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini")

    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=file-test-key\n", encoding="utf-8")

    config = get_openrouter_config(env_file=env_file)
    assert config.model == "openai/gpt-4.1-mini"


def test_connectivity_endpoint_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/ai/connectivity", json={"prompt": "What is 2 + 2?"})
    assert response.status_code == 401


def test_connectivity_endpoint_returns_mocked_openrouter_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)

    def _fake_query_openrouter(prompt: str) -> OpenRouterReply:
        assert prompt == "What is 2 + 2?"
        return OpenRouterReply(model="openai/gpt-oss-120b", text="4")

    monkeypatch.setattr("backend.app.routers.ai.query_openrouter", _fake_query_openrouter)

    response = client.post("/api/ai/connectivity", json={"prompt": "What is 2 + 2?"})
    assert response.status_code == 200
    assert response.json() == {"model": "openai/gpt-oss-120b", "response": "4"}


def test_connectivity_endpoint_reports_missing_api_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)

    def _raise_configuration_error(_: str) -> OpenRouterReply:
        raise OpenRouterConfigurationError("OpenRouter API key is not configured")

    monkeypatch.setattr("backend.app.routers.ai.query_openrouter", _raise_configuration_error)

    response = client.post("/api/ai/connectivity", json={"prompt": "What is 2 + 2?"})
    assert response.status_code == 500
    assert response.json()["detail"] == "OpenRouter API key is not configured"


def test_connectivity_endpoint_rejects_overlong_prompt(client: TestClient) -> None:
    _login(client)
    response = client.post("/api/ai/connectivity", json={"prompt": "x" * 4001})
    assert response.status_code == 422


def test_connectivity_endpoint_is_rate_limited(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    monkeypatch.setattr("backend.app.routers.ai._AI_RATE_LIMIT_MAX_REQUESTS", 2)

    def _fake_query_openrouter(prompt: str) -> OpenRouterReply:
        return OpenRouterReply(model="openai/gpt-oss-120b", text="4")

    monkeypatch.setattr("backend.app.routers.ai.query_openrouter", _fake_query_openrouter)

    first = client.post("/api/ai/connectivity", json={"prompt": "What is 2 + 2?"})
    second = client.post("/api/ai/connectivity", json={"prompt": "What is 2 + 2?"})
    third = client.post("/api/ai/connectivity", json={"prompt": "What is 2 + 2?"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
