from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from backend.app import board_store


def _scratch_engine_url(tmp_path: Path, name: str) -> str:
    return f"sqlite:///{tmp_path / name}"


def test_fresh_database_is_created_via_migrations(tmp_path: Path, monkeypatch) -> None:
    url = _scratch_engine_url(tmp_path, "fresh.db")
    engine = create_engine(url, future=True)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(board_store, "ENGINE", engine)

    board_store._ensure_schema()

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"users", "boards", "columns", "cards", "alembic_version"}.issubset(tables)

    board_uniques = {
        tuple(sorted(constraint["column_names"])) for constraint in inspector.get_unique_constraints("boards")
    }
    assert ("title", "user_id") in board_uniques


def test_preexisting_database_without_alembic_is_adopted_without_data_loss(
    tmp_path: Path, monkeypatch
) -> None:
    """This is the direct regression test for the critical finding (F1):
    a database created before Alembic was adopted (tables already exist,
    no alembic_version bookkeeping table, real rows present) must be
    stamped in place, never dropped and recreated.
    """
    url = _scratch_engine_url(tmp_path, "preexisting.db")
    engine = create_engine(url, future=True)

    # Simulate a database created by the old create_all()-only bootstrap.
    board_store.Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (username, password_hash) VALUES "
                "('preexisting-user', 'preexisting-hash')"
            )
        )

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(board_store, "ENGINE", engine)

    board_store._ensure_schema()

    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT username, password_hash FROM users WHERE username = 'preexisting-user'")
        ).one_or_none()

    assert row is not None
    assert row[0] == "preexisting-user"
    assert row[1] == "preexisting-hash"

    inspector = inspect(engine)
    assert "alembic_version" in inspector.get_table_names()


def test_ensure_schema_is_idempotent_and_never_drops_data(tmp_path: Path, monkeypatch) -> None:
    url = _scratch_engine_url(tmp_path, "idempotent.db")
    engine = create_engine(url, future=True)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(board_store, "ENGINE", engine)

    board_store._ensure_schema()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (username, password_hash) VALUES ('repeat-user', 'hash')")
        )

    # Calling _ensure_schema() again (e.g. on a second app startup) must not
    # touch existing rows.
    board_store._ensure_schema()

    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT username FROM users WHERE username = 'repeat-user'")
        ).one_or_none()
    assert row is not None
