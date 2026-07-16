# Database Design

## Purpose

This document defines the normalized SQLite schema for the Kanban board and reconciles the implemented state with the originally approved requirements.

## Scope

- Runtime database: SQLite
- ORM: SQLAlchemy
- Current implementation scope (MVP in code): single authenticated user flow with one board
- Planned normalization scope (approved target): users, boards, columns, cards

## Approved normalized target schema

### users

- id: INTEGER PRIMARY KEY
- username: TEXT NOT NULL UNIQUE
- password_hash: TEXT NOT NULL
- created_at: DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

Indexes:

- uq_users_username on username

Notes:

- Username uniqueness supports future multi-user expansion.
- Password storage should be hash-only; no plaintext.

### boards

- id: INTEGER PRIMARY KEY
- user_id: INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
- title: TEXT NOT NULL
- created_at: DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

Constraints:

- UNIQUE(user_id, title)

Indexes:

- idx_boards_user_id on user_id

Notes:

- Supports one-or-many boards per user later.

### columns

- id: TEXT PRIMARY KEY
- board_id: INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE
- title: TEXT NOT NULL
- position: INTEGER NOT NULL

Constraints:

- UNIQUE(board_id, position)

Indexes:

- idx_columns_board_id on board_id
- idx_columns_board_position on (board_id, position)

Notes:

- position gives deterministic column ordering.

### cards

- id: TEXT PRIMARY KEY
- column_id: TEXT NOT NULL REFERENCES columns(id) ON DELETE CASCADE
- title: TEXT NOT NULL
- details: TEXT NOT NULL
- position: INTEGER NOT NULL

Constraints:

- UNIQUE(column_id, position)

Indexes:

- idx_cards_column_id on column_id
- idx_cards_column_position on (column_id, position)

Notes:

- position gives deterministic card ordering within each column.

## Implemented schema (current code)

The current implementation includes these tables:

- boards
- columns
- cards

Implemented relationships:

- columns.board_id -> boards.id (ON DELETE CASCADE)
- cards.column_id -> columns.id (ON DELETE CASCADE)

Implemented ordering strategy:

- columns.position: zero-based order of columns within board
- cards.position: zero-based order of cards within a column

Bootstrap behavior:

- On startup, schema is created if missing.
- If no board exists, initial seeded board data is inserted.

## Gap analysis: approved target vs implemented state

### Missing users and ownership relationships

Status: missing in current implementation.

- users table is not yet implemented.
- boards.user_id ownership is not yet implemented.
- Current board is global single-board storage.

Impact:

- No per-user board ownership in DB yet.
- Acceptable for current MVP behavior, but this is a planned Part 6+ enhancement.

### Constraints and indexes missing in implementation

Status: partially missing.

Missing unique constraints:

- UNIQUE(board_id, position) on columns
- UNIQUE(column_id, position) on cards

Missing ownership constraints:

- UNIQUE(user_id, title) on boards (depends on users/user_id)

Missing indexes:

- idx_columns_board_id
- idx_columns_board_position
- idx_cards_column_id
- idx_cards_column_position
- idx_boards_user_id (depends on user_id)

Impact:

- Functionality works for MVP, but integrity/performance constraints are weaker than approved target.

## Cascade and delete behavior

Current implemented behavior:

- Deleting a board cascades to its columns.
- Deleting a column cascades to its cards.

Operational persistence behavior:

- Board save replaces persisted columns/cards with submitted ordered snapshot for deterministic ordering.

## Deterministic ordering strategy

- API payload includes ordered columns list and ordered cardIds per column.
- Persist writes position integers from payload order.
- Read reconstructs board by sorting columns and cards by position ascending.

Determinism guarantees:

- Same payload order produces same persisted order.
- Reloading returns columns/cards in stable order.

## Database bootstrap strategy

- On backend startup:
  - create_all for schema
  - if boards table has no rows, insert seeded initial board

- Test bootstrap utilities:
  - reset routine drops/recreates schema and re-seeds initial board

## Board JSON API representation

### GET /api/board response

```json
{
  "columns": [
    {
      "id": "col-backlog",
      "title": "Backlog",
      "cardIds": ["card-1", "card-2"]
    },
    {
      "id": "col-discovery",
      "title": "Discovery",
      "cardIds": ["card-3"]
    }
  ],
  "cards": {
    "card-1": {
      "id": "card-1",
      "title": "Align roadmap themes",
      "details": "Draft quarterly themes with impact statements and metrics."
    },
    "card-2": {
      "id": "card-2",
      "title": "Gather customer signals",
      "details": "Review support tags, sales notes, and churn feedback."
    },
    "card-3": {
      "id": "card-3",
      "title": "Prototype analytics view",
      "details": "Sketch initial dashboard layout and key drill-downs."
    }
  }
}
```

### PUT /api/board request body

The request body uses the same shape and ordering semantics as GET /api/board response.

## Representative sample records

### boards rows

| id | title      |
|----|------------|
| 1  | Main Board |

### columns rows

| id            | board_id | title       | position |
|---------------|----------|-------------|----------|
| col-backlog   | 1        | Backlog     | 0        |
| col-discovery | 1        | Discovery   | 1        |
| col-progress  | 1        | In Progress | 2        |
| col-review    | 1        | Review      | 3        |
| col-done      | 1        | Done        | 4        |

### cards rows

| id     | column_id     | title                  | details                                              | position |
|--------|---------------|------------------------|------------------------------------------------------|----------|
| card-1 | col-backlog   | Align roadmap themes   | Draft quarterly themes with impact statements...     | 0        |
| card-2 | col-backlog   | Gather customer signals| Review support tags, sales notes, and churn feedback.| 1        |
| card-3 | col-discovery | Prototype analytics... | Sketch initial dashboard layout and key drill-downs. | 0        |

## Endpoint safety note for board reset

- Endpoint: POST /api/board/reset
- Security policy now enforced:
  - Requires authenticated session.
  - Returns 404 unless ALLOW_TEST_RESET=1 is explicitly set.
- Intended use: deterministic automated tests only.
- Must not be enabled in normal application operation.
