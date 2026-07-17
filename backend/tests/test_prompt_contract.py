from backend.app.board_store import INITIAL_BOARD_DATA
from backend.app.structured_output import build_structured_prompt


def test_prompt_includes_required_fields_for_all_operations() -> None:
    prompt = build_structured_prompt(
        board=INITIAL_BOARD_DATA,
        user_message="test",
        history=[],
    )

    assert "create_card: id, type, card_id, column_id, title, details, position" in prompt
    assert "update_card: id, type, card_id, title and/or details" in prompt
    assert "move_card: id, type, card_id, column_id, position" in prompt
    assert "delete_card: id, type, card_id" in prompt
    assert "rename_column: id, type, column_id, title" in prompt


def test_prompt_includes_create_card_id_generation_instruction() -> None:
    prompt = build_structured_prompt(
        board=INITIAL_BOARD_DATA,
        user_message="test",
        history=[],
    )

    assert "For create_card only, generate a new deterministic card_id in this format: ai-card-<short-unique-suffix>." in prompt


def test_prompt_includes_complete_examples_for_each_operation_type() -> None:
    prompt = build_structured_prompt(
        board=INITIAL_BOARD_DATA,
        user_message="test",
        history=[],
    )

    assert "Complete valid JSON example for create_card:" in prompt
    assert "Complete valid JSON example for update_card:" in prompt
    assert "Complete valid JSON example for move_card:" in prompt
    assert "Complete valid JSON example for delete_card:" in prompt
    assert "Complete valid JSON example for rename_column:" in prompt
