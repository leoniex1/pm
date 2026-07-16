from pathlib import Path

import pytest

from backend.app import board_store


@pytest.fixture(autouse=True)
def reset_db() -> None:
    board_store.reset_database()


def test_default_database_path_resolves_to_backend_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_PATH", raising=False)

    db_url = board_store._database_url()
    expected_path = (Path(board_store.__file__).resolve().parents[1] / "data" / "kanban.db").resolve()

    assert db_url == f"sqlite:///{expected_path}"
    assert "backend/backend/data" not in db_url.replace("\\", "/")
