"""Initial schema: users, boards, columns, cards.

This migration intentionally mirrors, column-for-column and
constraint-for-constraint, the schema previously produced by
Base.metadata.create_all() so that databases created before Alembic was
adopted can be "stamped" as already being at this revision without any
table being touched (see board_store._ensure_schema()).

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-21

"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    op.create_table(
        "boards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.UniqueConstraint("user_id", "title", name="uq_boards_user_title"),
    )
    op.create_index("idx_boards_user_id", "boards", ["user_id"])

    op.create_table(
        "columns",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "board_id",
            sa.Integer(),
            sa.ForeignKey("boards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("board_id", "position", name="uq_columns_board_position"),
    )
    op.create_index("idx_columns_board_id", "columns", ["board_id"])
    op.create_index("idx_columns_board_position", "columns", ["board_id", "position"])

    op.create_table(
        "cards",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "column_id",
            sa.String(length=64),
            sa.ForeignKey("columns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("details", sa.String(length=2000), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("column_id", "position", name="uq_cards_column_position"),
    )
    op.create_index("idx_cards_column_id", "cards", ["column_id"])
    op.create_index("idx_cards_column_position", "cards", ["column_id", "position"])


def downgrade() -> None:
    op.drop_table("cards")
    op.drop_table("columns")
    op.drop_table("boards")
    op.drop_table("users")
