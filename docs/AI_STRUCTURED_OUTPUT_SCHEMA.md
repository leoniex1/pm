# Structured AI Output Contract (Part 9 Proposal)

## Status

- Approved and implemented in backend Part 9.
- Parser and mutation validation/application behavior now follow this contract.

## Scope

This contract defines the model output shape for AI-assisted Kanban responses.

Required output sections:
- `assistant_message`: natural-language reply to the user.
- `operations`: optional array of Kanban mutations.

Allowed MVP operation types only:
- `create_card`
- `update_card`
- `move_card`
- `delete_card`
- `rename_column`

No other operation types are allowed.

## Model Input Context (planned)

For each AI request, the backend will provide the model with:
- authenticated user's current ordered board JSON (`columns` order and `cardIds` order),
- current user message,
- conversation history (ordered list of prior user/assistant turns).

Ownership rule:
- Board context is loaded by authenticated `user_id` from session.
- The model sees only that user's board data.

## Output JSON shape

```json
{
  "assistant_message": "string",
  "operations": [
    {
      "id": "op_1",
      "type": "create_card"
    }
  ]
}
```

Field rules:
- `assistant_message`: required, non-empty string, max length 4000.
- `operations`: optional; when omitted backend treats as empty array.
- `operations` max length: 50.
- Every operation must include `id`: string matching `^[a-zA-Z0-9_-]{1,64}$`.
- Each operation object must contain only documented fields (`additionalProperties: false`).

## Operation definitions

### 1) create_card

Purpose:
- Create a new card in a column at a deterministic position.

Required fields:
- `id`: unique operation id
- `type`: `"create_card"`
- `card_id`: string, pattern `^[a-zA-Z0-9_-]{1,64}$`
- `column_id`: existing column id in current user's board
- `title`: non-empty string, max 200
- `details`: string, max 2000
- `position`: integer >= 0

Validation notes:
- `card_id` must not already exist in current user's board.
- `position` must be within insertion range for target column.

### 2) update_card

Purpose:
- Update title and/or details of an existing card.

Required fields:
- `id`: unique operation id
- `type`: `"update_card"`
- `card_id`: existing card id in current user's board

Optional fields:
- `title`: non-empty string, max 200
- `details`: string, max 2000

Validation notes:
- At least one of `title` or `details` must be present.

### 3) move_card

Purpose:
- Move an existing card to a target column and position.

Required fields:
- `id`: unique operation id
- `type`: `"move_card"`
- `card_id`: existing card id in current user's board
- `to_column_id`: existing column id in current user's board
- `position`: integer >= 0

Validation notes:
- `position` must be within insertion range in the destination column.

### 4) delete_card

Purpose:
- Delete an existing card.

Required fields:
- `id`: unique operation id
- `type`: `"delete_card"`
- `card_id`: existing card id in current user's board

### 5) rename_column

Purpose:
- Rename an existing column.

Required fields:
- `id`: unique operation id
- `type`: `"rename_column"`
- `column_id`: existing column id in current user's board
- `title`: non-empty string, max 120

## Validation rules (backend-side)

1. Parse response strictly as JSON object.
2. Reject if top-level keys are missing or unknown.
3. Validate `assistant_message` constraints.
4. Validate `operations` is an array (or omitted).
5. For each operation:
- `type` must be in allowed enum.
- Required fields for that `type` must be present.
- Unknown fields are rejected.
- Field types, lengths, patterns, and ranges must pass.
6. Enforce board ownership boundary checks:
- Every referenced `column_id` and `card_id` must belong to authenticated user's board.
7. Enforce semantic consistency checks:
- duplicate operation `id` values are rejected,
- duplicate `create_card.card_id` in one response is rejected,
- invalid position references are rejected,
- unsupported operation types are rejected.

## Malformed or unsafe output handling

If model output is malformed or unsafe:
- No board mutation is applied.
- Backend returns a safe response with no applied operations.
- Error is recorded server-side without secrets.
- API key is never included in logs, responses, or frontend payloads.

Unsafe includes (non-exhaustive):
- unknown operation type,
- unknown fields in operation objects,
- references to missing/non-owned cards or columns,
- attempts to encode SQL, file access, code execution, or non-Kanban instructions.

## Atomic application behavior

When operation execution is implemented (after approval), operations will be applied atomically:
- Full validation first, against authenticated user's current board.
- Apply all operations in one DB transaction.
- If any operation fails validation or execution, rollback entire transaction.
- Result: either all operations are applied, or none are applied.

## Ownership isolation guarantee

- Auth session provides `user_id`.
- Backend reads/writes board via user-scoped data access (`get_board(session, user_id)` and `save_board(session, user_id, ...)`).
- Operation references are resolved only against that board snapshot.
- Cross-user ids are treated as invalid references and rejected.

## Example valid responses

### A) Chat-only (no mutations)

```json
{
  "assistant_message": "You currently have 3 cards in Discovery.",
  "operations": []
}
```

### B) Rename column + move card

```json
{
  "assistant_message": "I renamed the column and moved the card.",
  "operations": [
    {
      "id": "op-1",
      "type": "rename_column",
      "column_id": "col-progress",
      "title": "Doing"
    },
    {
      "id": "op-2",
      "type": "move_card",
      "card_id": "card-6",
      "to_column_id": "col-review",
      "position": 0
    }
  ]
}
```

### C) Create card then update card details

```json
{
  "assistant_message": "Added a new card with details.",
  "operations": [
    {
      "id": "op-1",
      "type": "create_card",
      "card_id": "card-ops-1",
      "column_id": "col-backlog",
      "title": "Prepare sprint brief",
      "details": "Draft goals and acceptance criteria.",
      "position": 0
    },
    {
      "id": "op-2",
      "type": "update_card",
      "card_id": "card-ops-1",
      "details": "Draft goals, acceptance criteria, and owners."
    }
  ]
}
```

## Example invalid responses

### A) Unsupported operation type

```json
{
  "assistant_message": "Done.",
  "operations": [
    {
      "id": "op-1",
      "type": "drop_table",
      "table": "cards"
    }
  ]
}
```

Reason:
- `drop_table` is not in allowed enum.

### B) Missing deterministic required field

```json
{
  "assistant_message": "Moved the card.",
  "operations": [
    {
      "id": "op-1",
      "type": "move_card",
      "card_id": "card-1",
      "to_column_id": "col-done"
    }
  ]
}
```

Reason:
- `position` is required for `move_card`.

### C) Unknown field / unsafe instruction

```json
{
  "assistant_message": "I will run a command.",
  "operations": [
    {
      "id": "op-1",
      "type": "update_card",
      "card_id": "card-2",
      "title": "Updated",
      "shell_command": "rm -rf /"
    }
  ]
}
```

Reason:
- `shell_command` is unsupported and rejected via `additionalProperties: false`.

### D) Cross-user reference (not on authenticated board)

```json
{
  "assistant_message": "Moved a card.",
  "operations": [
    {
      "id": "op-1",
      "type": "move_card",
      "card_id": "foreign-user-card",
      "to_column_id": "col-review",
      "position": 0
    }
  ]
}
```

Reason:
- `card_id` does not resolve in authenticated user's board.

## Approval gate checklist

This proposal explicitly defines:
- `assistant_message`
- `operations` array
- operation-level `id` for auditing/debugging
- allowed operation types
- deterministic required fields per operation
- validation rules
- valid/invalid examples
- malformed/unsafe handling
- atomic apply behavior
- ownership isolation boundaries

The implemented backend parser/mutator must remain aligned with this document.
