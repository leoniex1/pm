from __future__ import annotations

import os
from pathlib import Path

import bcrypt
from alembic import command
from alembic.config import Config
from pydantic import BaseModel, model_validator
from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    event,
    inspect,
)
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

    @model_validator(mode="after")
    def _validate_referential_integrity(self) -> "BoardData":
        column_ids = [column.id for column in self.columns]
        if len(column_ids) != len(set(column_ids)):
            raise ValueError("Duplicate column id in board payload")

        all_card_refs: list[str] = []
        for column in self.columns:
            all_card_refs.extend(column.cardIds)

        if len(all_card_refs) != len(set(all_card_refs)):
            raise ValueError("Duplicate card id referenced across columns")

        referenced_ids = set(all_card_refs)
        card_dict_ids = set(self.cards.keys())

        missing = referenced_ids - card_dict_ids
        if missing:
            raise ValueError(f"cardIds reference missing card entries: {sorted(missing)}")

        orphaned = card_dict_ids - referenced_ids
        if orphaned:
            raise ValueError(f"cards entries are not referenced by any column: {sorted(orphaned)}")

        return self


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


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    boards: Mapped[list[Board]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Board(Base):
    __tablename__ = "boards"
    __table_args__ = (
        UniqueConstraint("user_id", "title", name="uq_boards_user_title"),
        Index("idx_boards_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(120), default="Main Board")
    user: Mapped[User] = relationship(back_populates="boards")
    columns: Mapped[list[Column]] = relationship(
        back_populates="board", cascade="all, delete-orphan"
    )


class Column(Base):
    __tablename__ = "columns"
    __table_args__ = (
        UniqueConstraint("board_id", "position", name="uq_columns_board_position"),
        Index("idx_columns_board_id", "board_id"),
        Index("idx_columns_board_position", "board_id", "position"),
    )

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
    __table_args__ = (
        UniqueConstraint("column_id", "position", name="uq_cards_column_position"),
        Index("idx_cards_column_id", "column_id"),
        Index("idx_cards_column_position", "column_id", "position"),
    )

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

    backend_root = Path(__file__).resolve().parents[1]
    configured_path = os.getenv("DATABASE_PATH")
    if configured_path:
        db_path = Path(configured_path)
        if not db_path.is_absolute():
            db_path = (backend_root / db_path).resolve()
    else:
        db_path = backend_root / "data" / "kanban.db"

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


ENGINE = create_engine(_database_url(), future=True)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, future=True)

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_ALEMBIC_INI_PATH = _BACKEND_ROOT / "alembic.ini"
_MIGRATIONS_DIR = _BACKEND_ROOT / "migrations"


@event.listens_for(ENGINE, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _alembic_config() -> Config:
    config = Config(str(_ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", _database_url())
    return config


def _ensure_schema() -> None:
    """Bring the schema up to date without ever dropping existing data.

    - Brand-new database (no tables at all): run migrations to create the schema.
    - Database already managed by Alembic: run any pending migrations.
    - Database created before Alembic was adopted (tables exist, no
      alembic_version bookkeeping table): the initial migration is defined to
      exactly match that pre-Alembic schema, so it is safe to "stamp" it as
      already being at head without touching any table or row.
    """
    inspector = inspect(ENGINE)
    table_names = set(inspector.get_table_names())
    config = _alembic_config()

    with ENGINE.connect() as connection:
        config.attributes["connection"] = connection

        if "alembic_version" in table_names:
            command.upgrade(config, "head")
            return

        expected_tables = {"users", "boards", "columns", "cards"}
        if expected_tables.issubset(table_names):
            command.stamp(config, "head")
            return

        command.upgrade(config, "head")


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _ensure_user(session: Session, username: str, password: str) -> User:
    user = session.query(User).filter(User.username == username).one_or_none()
    if user is None:
        user = User(username=username, password_hash=_hash_password(password))
        session.add(user)
        session.flush()
    return user


def _seed_board_data_for_user(session: Session, user_id: int) -> BoardData:
    """Build the initial board to seed for a user's first board.

    columns.id and cards.id are primary keys that are unique across the
    whole table, not scoped per board, so INITIAL_BOARD_DATA's fixed ids can
    only be reused as-is for the very first board ever seeded. Any
    subsequent user gets an equivalent board with ids made unique to them,
    so every user (not just a single hardcoded account) reliably gets a
    populated starter board.
    """
    canonical_column_ids = [column.id for column in INITIAL_BOARD_DATA.columns]
    collision = session.query(Column.id).filter(Column.id.in_(canonical_column_ids)).first()
    if collision is None:
        return INITIAL_BOARD_DATA

    suffix = f"-u{user_id}"
    card_id_map = {card_id: f"{card_id}{suffix}" for card_id in INITIAL_BOARD_DATA.cards}

    columns = [
        ColumnData(
            id=f"{column.id}{suffix}",
            title=column.title,
            cardIds=[card_id_map[card_id] for card_id in column.cardIds],
        )
        for column in INITIAL_BOARD_DATA.columns
    ]
    cards = {
        card_id_map[card_id]: CardData(
            id=card_id_map[card_id], title=card.title, details=card.details
        )
        for card_id, card in INITIAL_BOARD_DATA.cards.items()
    }
    return BoardData(columns=columns, cards=cards)


def _ensure_board_for_user(session: Session, user_id: int) -> Board:
    board = session.query(Board).filter(Board.user_id == user_id).order_by(Board.id.asc()).first()
    if board is None:
        board = Board(user_id=user_id, title="Main Board")
        session.add(board)
        session.flush()

        save_board(session, user_id, _seed_board_data_for_user(session, user_id))

        board = session.query(Board).filter(Board.user_id == user_id).order_by(Board.id.asc()).first()
        if board is None:
            raise RuntimeError("Board initialization failed")
    return board


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    user = session.query(User).filter(User.username == username).one_or_none()
    if user is None:
        return None
    if not _verify_password(password, user.password_hash):
        return None
    return user


def get_user_by_id(session: Session, user_id: int) -> User | None:
    return session.query(User).filter(User.id == user_id).one_or_none()


def init_database() -> None:
    _ensure_schema()
    with SessionLocal() as session:
        user = _ensure_user(session, "user", "password")
        _ensure_board_for_user(session, user.id)
        session.commit()


def reset_database() -> None:
    """Test-only full reset. Never called from the normal startup path."""
    Base.metadata.drop_all(bind=ENGINE)
    Base.metadata.create_all(bind=ENGINE)

    config = _alembic_config()
    with ENGINE.connect() as connection:
        config.attributes["connection"] = connection
        command.stamp(config, "head")

    with SessionLocal() as session:
        user = _ensure_user(session, "user", "password")
        _ensure_board_for_user(session, user.id)
        session.commit()


def get_board(session: Session, user_id: int) -> BoardData:
    board = _ensure_board_for_user(session, user_id)

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


def save_board(session: Session, user_id: int, board_data: BoardData, commit: bool = True) -> BoardData:
    board = _ensure_board_for_user(session, user_id)

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

    if commit:
        session.commit()
    else:
        session.flush()
    return get_board(session, user_id)
