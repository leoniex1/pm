import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from backend.app.board_store import (
    INITIAL_BOARD_DATA,
    BoardData,
    Board,
    CardData,
    Card,
    ColumnData,
    Column,
    ENGINE,
    SessionLocal,
    User,
    get_board,
    reset_database,
    save_board,
)
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


def test_board_ownership_is_isolated_by_user() -> None:
    with SessionLocal() as session:
        user_one = session.query(User).filter(User.username == "user").one()
        user_two = User(username="another", password_hash="password")
        session.add(user_two)
        session.flush()

        other_user_board = BoardData(
            columns=[ColumnData(id="u2-col-1", title="Another User Board", cardIds=["u2-card-1"])],
            cards={
                "u2-card-1": CardData(
                    id="u2-card-1",
                    title="User 2 card",
                    details="Owned by second user",
                )
            },
        )
        save_board(session, user_two.id, other_user_board)

        board_two = get_board(session, user_two.id)
        assert board_two.columns[0].title == "Another User Board"

        board_one = get_board(session, user_one.id)
        assert board_one.columns[0].title == "Backlog"


def test_one_board_per_user_behavior() -> None:
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "user").one()
        board = get_board(session, user.id)
        board.columns[0].title = "Only Board"
        save_board(session, user.id, board)

        board_count = session.query(Board).filter(Board.user_id == user.id).count()
        assert board_count == 1


def test_foreign_keys_and_cascade_behavior() -> None:
    with SessionLocal() as session:
        user = User(username="cascade", password_hash="password")
        session.add(user)
        session.flush()

        user_board = BoardData(
            columns=[ColumnData(id="cascade-col-1", title="Cascade", cardIds=["cascade-card-1"])],
            cards={
                "cascade-card-1": CardData(
                    id="cascade-card-1",
                    title="Cascade card",
                    details="Cascade details",
                )
            },
        )
        save_board(session, user.id, user_board)
        board_id = session.query(Board).filter(Board.user_id == user.id).one().id

        column_count = (
            session.query(Column).join(Board, Column.board_id == Board.id).filter(Board.user_id == user.id).count()
        )
        card_count = (
            session.query(Card)
            .join(Column, Card.column_id == Column.id)
            .join(Board, Column.board_id == Board.id)
            .filter(Board.user_id == user.id)
            .count()
        )
        assert column_count > 0
        assert card_count > 0

        session.delete(user)
        session.commit()

        remaining_board = session.query(Board).filter(Board.id == board_id).count()
        remaining_columns = (
            session.query(Column).join(Board, Column.board_id == Board.id).filter(Board.user_id == user.id).count()
        )
        remaining_cards = (
            session.query(Card)
            .join(Column, Card.column_id == Column.id)
            .join(Board, Column.board_id == Board.id)
            .filter(Board.user_id == user.id)
            .count()
        )
        assert remaining_board == 0
        assert remaining_columns == 0
        assert remaining_cards == 0


def test_uniqueness_constraints_and_indexes_exist() -> None:
    inspector = inspect(ENGINE)

    board_uniques = {tuple(sorted(constraint["column_names"])) for constraint in inspector.get_unique_constraints("boards")}
    assert ("title", "user_id") in board_uniques

    column_uniques = {
        tuple(sorted(constraint["column_names"]))
        for constraint in inspector.get_unique_constraints("columns")
    }
    assert ("board_id", "position") in column_uniques

    card_uniques = {
        tuple(sorted(constraint["column_names"]))
        for constraint in inspector.get_unique_constraints("cards")
    }
    assert ("column_id", "position") in card_uniques

    index_names = {
        *[index["name"] for index in inspector.get_indexes("boards")],
        *[index["name"] for index in inspector.get_indexes("columns")],
        *[index["name"] for index in inspector.get_indexes("cards")],
    }

    assert "idx_boards_user_id" in index_names
    assert "idx_columns_board_id" in index_names
    assert "idx_columns_board_position" in index_names
    assert "idx_cards_column_id" in index_names
    assert "idx_cards_column_position" in index_names


def test_unique_position_constraints_enforced() -> None:
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "user").one()
        board = session.query(Board).filter(Board.user_id == user.id).one()

        session.add(
            Column(
                id="dup-pos-column",
                board_id=board.id,
                title="Duplicate",
                position=0,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        column = (
            session.query(Column)
            .filter(Column.board_id == board.id)
            .order_by(Column.position.asc())
            .first()
        )
        assert column is not None

        session.add(
            Card(
                id="dup-pos-card",
                column_id=column.id,
                title="Duplicate Card",
                details="Duplicate position",
                position=0,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
