from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.app.board_store import BoardData, CardData, ColumnData


class StructuredOutputError(Exception):
    pass


class _OperationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]{1,64}$")


class CreateCardOperation(_OperationBase):
    type: Literal["create_card"]
    card_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    column_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    details: str = Field(max_length=2000)
    position: int = Field(ge=0)


class UpdateCardOperation(_OperationBase):
    type: Literal["update_card"]
    card_id: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    details: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _validate_has_update_field(self) -> "UpdateCardOperation":
        if self.title is None and self.details is None:
            raise ValueError("update_card must include title or details")
        return self


class MoveCardOperation(_OperationBase):
    type: Literal["move_card"]
    card_id: str = Field(min_length=1, max_length=64)
    to_column_id: str = Field(min_length=1, max_length=64)
    position: int = Field(ge=0)


class DeleteCardOperation(_OperationBase):
    type: Literal["delete_card"]
    card_id: str = Field(min_length=1, max_length=64)


class RenameColumnOperation(_OperationBase):
    type: Literal["rename_column"]
    column_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)


Operation = Annotated[
    CreateCardOperation
    | UpdateCardOperation
    | MoveCardOperation
    | DeleteCardOperation
    | RenameColumnOperation,
    Field(discriminator="type"),
]


class StructuredAIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_message: str = Field(min_length=1, max_length=4000)
    operations: list[Operation] = Field(default_factory=list, max_length=50)


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    message: str = Field(min_length=1, max_length=4000)


@dataclass
class _BoardState:
    column_order: list[str]
    column_titles: dict[str, str]
    column_cards: dict[str, list[str]]
    cards: dict[str, CardData]


def build_structured_prompt(board: BoardData, user_message: str, history: list[ConversationTurn]) -> str:
    board_json = board.model_dump(mode="json")
    history_json = [turn.model_dump(mode="json") for turn in history]

    contract = {
        "assistant_message": "string",
        "operations": [
            {
                "id": "op_1",
                "type": "create_card|update_card|move_card|delete_card|rename_column",
            }
        ],
    }

    return (
        "You are a kanban assistant. Respond with JSON only. No markdown, no prose outside JSON.\n"
        "Return an object with this shape exactly: "
        + json.dumps(contract)
        + "\n"
        "Rules:\n"
        "- operations may be empty.\n"
        "- Every operation must include a unique id.\n"
        "- Allowed operation types only: create_card, update_card, move_card, delete_card, rename_column.\n"
        "- Never include unknown fields.\n"
        "- Do not request SQL, file access, code execution, or shell commands.\n"
        "Context board JSON: "
        + json.dumps(board_json)
        + "\n"
        "Conversation history JSON: "
        + json.dumps(history_json)
        + "\n"
        "User message: "
        + user_message
    )


def parse_structured_response(raw_text: str) -> StructuredAIResponse:
    json_payload = _extract_json_payload(raw_text)
    try:
        raw_obj = json.loads(json_payload)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError("Model response was not valid JSON") from exc

    try:
        return StructuredAIResponse.model_validate(raw_obj)
    except ValidationError as exc:
        raise StructuredOutputError(f"Structured response validation failed: {exc.errors()}") from exc


def _extract_json_payload(raw_text: str) -> str:
    stripped = raw_text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            inner = "\n".join(lines[1:-1]).strip()
            if inner.startswith("json"):
                inner = inner[4:].strip()
            return inner
    return stripped


def validate_and_apply_operations(board: BoardData, operations: list[Operation]) -> BoardData:
    state = _to_state(board)

    operation_ids: set[str] = set()
    create_ids: set[str] = set()

    for operation in operations:
        if operation.id in operation_ids:
            raise StructuredOutputError(f"Duplicate operation id: {operation.id}")
        operation_ids.add(operation.id)

        if isinstance(operation, CreateCardOperation):
            _apply_create_card(state, operation, create_ids)
        elif isinstance(operation, UpdateCardOperation):
            _apply_update_card(state, operation)
        elif isinstance(operation, MoveCardOperation):
            _apply_move_card(state, operation)
        elif isinstance(operation, DeleteCardOperation):
            _apply_delete_card(state, operation)
        elif isinstance(operation, RenameColumnOperation):
            _apply_rename_column(state, operation)
        else:
            raise StructuredOutputError("Unsupported operation type")

    return _from_state(state)


def _apply_create_card(state: _BoardState, operation: CreateCardOperation, create_ids: set[str]) -> None:
    if operation.card_id in create_ids:
        raise StructuredOutputError(f"Duplicate create_card id: {operation.card_id}")
    create_ids.add(operation.card_id)

    if operation.card_id in state.cards:
        raise StructuredOutputError(f"Card id already exists: {operation.card_id}")
    if operation.column_id not in state.column_cards:
        raise StructuredOutputError(f"Unknown or cross-board column reference: {operation.column_id}")

    card_ids = state.column_cards[operation.column_id]
    if operation.position > len(card_ids):
        raise StructuredOutputError("Invalid position for create_card")

    state.cards[operation.card_id] = CardData(
        id=operation.card_id,
        title=operation.title,
        details=operation.details,
    )
    card_ids.insert(operation.position, operation.card_id)


def _apply_update_card(state: _BoardState, operation: UpdateCardOperation) -> None:
    card = state.cards.get(operation.card_id)
    if card is None:
        raise StructuredOutputError(f"Unknown or cross-board card reference: {operation.card_id}")

    if operation.title is not None:
        card.title = operation.title
    if operation.details is not None:
        card.details = operation.details


def _apply_move_card(state: _BoardState, operation: MoveCardOperation) -> None:
    if operation.card_id not in state.cards:
        raise StructuredOutputError(f"Unknown or cross-board card reference: {operation.card_id}")
    if operation.to_column_id not in state.column_cards:
        raise StructuredOutputError(f"Unknown or cross-board column reference: {operation.to_column_id}")

    source_column_id = _find_card_column(state, operation.card_id)
    if source_column_id is None:
        raise StructuredOutputError(f"Card missing from column index: {operation.card_id}")

    source_cards = state.column_cards[source_column_id]
    source_cards.remove(operation.card_id)

    target_cards = state.column_cards[operation.to_column_id]
    if operation.position > len(target_cards):
        source_cards.append(operation.card_id)
        raise StructuredOutputError("Invalid position for move_card")

    target_cards.insert(operation.position, operation.card_id)


def _apply_delete_card(state: _BoardState, operation: DeleteCardOperation) -> None:
    if operation.card_id not in state.cards:
        raise StructuredOutputError(f"Unknown or cross-board card reference: {operation.card_id}")

    source_column_id = _find_card_column(state, operation.card_id)
    if source_column_id is None:
        raise StructuredOutputError(f"Card missing from column index: {operation.card_id}")

    state.column_cards[source_column_id].remove(operation.card_id)
    del state.cards[operation.card_id]


def _apply_rename_column(state: _BoardState, operation: RenameColumnOperation) -> None:
    if operation.column_id not in state.column_titles:
        raise StructuredOutputError(f"Unknown or cross-board column reference: {operation.column_id}")
    state.column_titles[operation.column_id] = operation.title


def _find_card_column(state: _BoardState, card_id: str) -> str | None:
    for column_id, card_ids in state.column_cards.items():
        if card_id in card_ids:
            return column_id
    return None


def _to_state(board: BoardData) -> _BoardState:
    column_order = [column.id for column in board.columns]
    column_titles = {column.id: column.title for column in board.columns}
    column_cards = {column.id: list(column.cardIds) for column in board.columns}
    cards = {card_id: deepcopy(card) for card_id, card in board.cards.items()}
    return _BoardState(
        column_order=column_order,
        column_titles=column_titles,
        column_cards=column_cards,
        cards=cards,
    )


def _from_state(state: _BoardState) -> BoardData:
    columns: list[ColumnData] = []
    for column_id in state.column_order:
        columns.append(
            ColumnData(
                id=column_id,
                title=state.column_titles[column_id],
                cardIds=list(state.column_cards[column_id]),
            )
        )

    return BoardData(columns=columns, cards=state.cards)
