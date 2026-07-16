from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


class CardData(BaseModel):
    id: str
    title: str
    details: str


class ColumnData(BaseModel):
    id: str
    title: str
    cardIds: list[str]


class BoardData(BaseModel):
    columns: list[ColumnData]
    cards: dict[str, CardData]


INITIAL_BOARD_DATA = BoardData(
    columns=[
        ColumnData(id="col-backlog", title="Backlog", cardIds=["card-1", "card-2"]),
        ColumnData(id="col-discovery", title="Discovery", cardIds=["card-3"]),
        ColumnData(id="col-progress", title="In Progress", cardIds=["card-4", "card-5"]),
        ColumnData(id="col-review", title="Review", cardIds=["card-6"]),
        ColumnData(id="col-done", title="Done", cardIds=["card-7", "card-8"]),
    ],
    cards={
        "card-1": CardData(
            id="card-1",
            title="Align roadmap themes",
            details="Draft quarterly themes with impact statements and metrics.",
        ),
        "card-2": CardData(
            id="card-2",
            title="Gather customer signals",
            details="Review support tags, sales notes, and churn feedback.",
        ),
        "card-3": CardData(
            id="card-3",
            title="Prototype analytics view",
            details="Sketch initial dashboard layout and key drill-downs.",
        ),
        "card-4": CardData(
            id="card-4",
            title="Refine status language",
            details="Standardize column labels and tone across the board.",
        ),
        "card-5": CardData(
            id="card-5",
            title="Design card layout",
            details="Add hierarchy and spacing for scanning dense lists.",
        ),
        "card-6": CardData(
            id="card-6",
            title="QA micro-interactions",
            details="Verify hover, focus, and loading states.",
        ),
        "card-7": CardData(
            id="card-7",
            title="Ship marketing page",
            details="Final copy approved and asset pack delivered.",
        ),
        "card-8": CardData(
            id="card-8",
            title="Close onboarding sprint",
            details="Document release notes and share internally.",
        ),
    },
)


class Base(DeclarativeBase):
    pass


class Board(Base):
    __tablename__ = "boards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120), default="Main Board")
    columns: Mapped[list[Column]] = relationship(
        back_populates="board", cascade="all, delete-orphan"
    )


class Column(Base):
    __tablename__ = "columns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer)

    board: Mapped[Board] = relationship(back_populates="columns")
    cards: Mapped[list[Card]] = relationship(
        back_populates="column", cascade="all, delete-orphan"
    )


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    column_id: Mapped[str] = mapped_column(ForeignKey("columns.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    details: Mapped[str] = mapped_column(String(2000))
    position: Mapped[int] = mapped_column(Integer)

    column: Mapped[Column] = relationship(back_populates="cards")


def _database_url() -> str:
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        return explicit_url

    db_path = Path(os.getenv("DATABASE_PATH", "backend/data/kanban.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


ENGINE = create_engine(_database_url(), future=True)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, future=True)


def init_database() -> None:
    Base.metadata.create_all(bind=ENGINE)
    with SessionLocal() as session:
        if session.query(Board).count() == 0:
            save_board(session, INITIAL_BOARD_DATA)


def reset_database() -> None:
    Base.metadata.drop_all(bind=ENGINE)
    Base.metadata.create_all(bind=ENGINE)
    with SessionLocal() as session:
        save_board(session, INITIAL_BOARD_DATA)


def get_board(session: Session) -> BoardData:
    board = session.query(Board).order_by(Board.id.asc()).first()
    if board is None:
        save_board(session, INITIAL_BOARD_DATA)
        board = session.query(Board).order_by(Board.id.asc()).first()
        if board is None:
            raise RuntimeError("Board initialization failed")

    columns = (
        session.query(Column)
        .filter(Column.board_id == board.id)
        .order_by(Column.position.asc())
        .all()
    )

    cards_by_id: dict[str, CardData] = {}
    result_columns: list[ColumnData] = []

    for column in columns:
        cards = (
            session.query(Card)
            .filter(Card.column_id == column.id)
            .order_by(Card.position.asc())
            .all()
        )
        card_ids: list[str] = []
        for card in cards:
            card_ids.append(card.id)
            cards_by_id[card.id] = CardData(id=card.id, title=card.title, details=card.details)

        result_columns.append(ColumnData(id=column.id, title=column.title, cardIds=card_ids))

    return BoardData(columns=result_columns, cards=cards_by_id)


def save_board(session: Session, board_data: BoardData) -> BoardData:
    board = session.query(Board).order_by(Board.id.asc()).first()
    if board is None:
        board = Board(title="Main Board")
        session.add(board)
        session.flush()

    session.query(Card).filter(
        Card.column_id.in_(
            session.query(Column.id).filter(Column.board_id == board.id)
        )
    ).delete(synchronize_session=False)
    session.query(Column).filter(Column.board_id == board.id).delete(synchronize_session=False)
    session.flush()

    for column_position, column_data in enumerate(board_data.columns):
        column = Column(
            id=column_data.id,
            board_id=board.id,
            title=column_data.title,
            position=column_position,
        )
        session.add(column)

        for card_position, card_id in enumerate(column_data.cardIds):
            card_data = board_data.cards.get(card_id)
            if card_data is None:
                continue

            card = Card(
                id=card_data.id,
                column_id=column.id,
                title=card_data.title,
                details=card_data.details,
                position=card_position,
            )
            session.add(card)

    session.commit()
    return get_board(session)
