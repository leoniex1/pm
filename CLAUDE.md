# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A single-user (MVP) Project Management web app: a Kanban board with an AI chat sidebar that can
create/edit/move cards. NextJS frontend + Python FastAPI backend, packaged into one Docker container
(FastAPI serves the statically-exported NextJS site at `/` as well as the API). SQLite is the database.
AI calls go through OpenRouter (`openai/gpt-oss-120b` by default).

Read `AGENTS.md` (root) for business requirements/decisions, `docs/PLAN.md` for the phased execution
plan/status, `docs/DATABASE_DESIGN.md` for the DB schema, and `docs/AI_STRUCTURED_OUTPUT_SCHEMA.md` for
the AI structured-output contract. Folder-level `AGENTS.md` files (`backend/AGENTS.md`,
`frontend/AGENTS.md`, `scripts/AGENTS.md`) contain architecture/reference notes for that folder — check
them before diving into that area.

## Commands

### Backend (run from repo root — imports are rooted at `backend.app.*`)

```bash
pip install -r backend/requirements.txt
pytest backend/tests                     # all backend tests
pytest backend/tests/test_board.py       # single file
pytest backend/tests/test_board.py::test_seeded_board_available_after_login  # single test
```

Tests must be run from the repository root (not `backend/`) because test modules import via
`backend.app.board_store`, `backend.app.main`, etc.

### Frontend (run from `frontend/`)

```bash
npm install
npm run dev          # dev server
npm run build        # production build (also produces the static export used by Docker)
npm run lint
npm run test:unit    # vitest
npm run test:e2e     # playwright
npm run test:all     # unit + e2e
```

### Docker (single container, run from repo root)

```powershell
scripts/start-windows.ps1   # build image `pm-mvp`, run on :8000, mounts backend/data, uses .env
scripts/stop-windows.ps1
```

Equivalent `start-linux.sh`/`start-mac.sh` and `stop-linux.sh`/`stop-mac.sh` exist for other OSes.
`OPENROUTER_API_KEY` (required) and `OPENROUTER_MODEL` (optional, default `openai/gpt-oss-120b`) are
read from the project-root `.env` file / environment.

## Architecture

### Request flow and auth

- `backend/app/main.py` is the single FastAPI entrypoint: auth endpoints, board CRUD, AI endpoints, and
  the catch-all static-file server for the exported NextJS app all live here.
- Auth is a server-side cookie session (`SessionMiddleware`), hardcoded credentials `user`/`password`
  for the MVP. There is no JWT/localStorage-based auth guard — session state is authoritative.
- Every board/AI route requires an authenticated session and resolves `user_id` from the session, not
  from client-supplied data.
- The catch-all `GET /{full_path:path}` route serves the exported frontend, redirecting to `/login` for
  unauthenticated requests to non-public paths, with an allowlist for public paths (`/login`,
  `/favicon.ico`, `/robots.txt`, `_next/*` assets).

### Board persistence (`backend/app/board_store.py`)

- Normalized SQLAlchemy schema: `users` -> `boards` -> `columns` -> `cards`, cascading deletes, with
  `position` integer columns giving deterministic ordering (unique per parent scope: `(board_id,
  position)` for columns, `(column_id, position)` for cards).
- The JSON API shape (`BoardData`: `columns: ColumnData[]` + `cards: dict[id, CardData]`, where each
  column holds an ordered `cardIds` list) is intentionally denormalized/order-based — it does not mirror
  the DB row shape. `get_board` reconstructs this shape from position-ordered DB rows; `save_board` does
  a full delete-and-reinsert of a user's columns/cards on every write, deriving `position` from array
  order. There is no partial/diffed update — every board write replaces the whole columns/cards set for
  that user's board.
- MVP is one board per user; multi-board support is schema-ready (`boards.user_id` + unique
  `(user_id, title)`) but not exposed.
- `init_database()` runs on app startup: creates schema if missing/mismatched (see
  `_schema_matches_expected`) and seeds the hardcoded `user`/`password` account with `INITIAL_BOARD_DATA`
  if no board exists yet.
- `POST /api/board/reset` only works when `ALLOW_TEST_RESET=1` — it's test-only and must stay disabled
  in normal operation.

### AI structured output (`backend/app/structured_output.py`)

This is the core safety-critical piece of the backend: it turns free-form model output into safe,
atomic board mutations.

- `build_structured_prompt` assembles the board JSON, conversation history, and a strict "JSON-only, no
  markdown" contract with per-operation-type required-field lists and full JSON examples, into a single
  prompt string sent to OpenRouter.
- Allowed operations: `create_card`, `update_card`, `move_card`, `delete_card`, `rename_column` — each a
  discriminated-union Pydantic model with `extra="forbid"` and a required unique `id` (for audit/
  debugging, distinct from `card_id`/`column_id`).
- `parse_structured_response` strictly validates the model's JSON against `StructuredAIResponse`
  (`assistant_message` + `operations[]`); any parse/validation failure raises `StructuredOutputError` ->
  surfaced to the frontend as HTTP 422, with the board left untouched.
- `validate_and_apply_operations` applies operations to an in-memory `_BoardState` snapshot
  sequentially, validating each against current state (rejecting unknown/cross-board card or column ids,
  duplicate operation/create ids, out-of-range positions) before it ever reaches the DB, then the whole
  resulting board is persisted in one transaction (`main.py` wraps `save_board(..., commit=False)` in
  `session.begin()`). A validation failure anywhere aborts the entire batch — operations are all-or-
  nothing, never partially applied.
- Safety contract for referencing nonexistent entities: prefer the model returning `operations: []` (a
  no-op, HTTP 200) rather than fabricating an operation against something that doesn't exist.
- Known residual risk (see `docs/PLAN.md`): real model responses can intermittently fail strict JSON
  parsing, surfacing as a sidebar error without corrupting board state — this is treated as acceptable
  for the MVP, not a bug to silently work around by loosening validation.

### OpenRouter client (`backend/app/openrouter_service.py`)

- Config (`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`) resolves from environment variables first, then
  falls back to parsing the project-root `.env` file directly (not via a dotenv-loading library) — this
  fallback exists so the backend works both in Docker (`--env-file`) and when run locally without the
  env vars pre-exported.
- `query_openrouter` is a thin synchronous wrapper around one POST to the OpenRouter chat-completions
  endpoint; configuration errors and request/response-shape errors are distinct exception types
  (`OpenRouterConfigurationError` vs `OpenRouterRequestError`) mapped to different HTTP status codes in
  `main.py` (500 vs 502).

### Frontend (`frontend/src`)

- `KanbanBoard` is the single state container: it owns board state (fetched via `GET /api/board`,
  persisted via `PUT /api/board`), drag/drop orchestration (`@dnd-kit`), and wires the AI sidebar's send
  handler to trigger a board reload after AI-driven mutations.
- Board shape mirrors the backend JSON contract exactly: `columns: Column[]` with ordered `cardIds`,
  plus `cards: Record<string, Card>` keyed by id. `moveCard` in `src/lib/kanban.ts` is the single source
  of truth for reorder/move logic (intra-column reorder, inter-column move, drop-onto-column-append) and
  is unit-tested independently of the DOM.
- `AiChatSidebar` keeps chat history in memory only for the current page session (no persisted
  transcript) and calls `POST /api/ai/respond` with `{ message, history }`; a returned board triggers an
  immediate reload in `KanbanBoard`.
- All API calls are sent with credentials (cookie session); there is no client-side auth token.
- Color tokens live in `src/app/globals.css` — keep changes aligned with the palette in the root
  `AGENTS.md` (accent yellow `#ecad0a`, blue `#209dd7`, purple `#753991`, dark navy `#032147`, gray
  `#888888`).

## Coding standards (from root `AGENTS.md`)

- Use latest stable library versions and idiomatic current approaches.
- Keep it simple: no over-engineering, no unnecessary defensive programming, no speculative features.
- No emojis, anywhere, ever.
- When debugging, find the root cause before applying a fix — do not guess-and-check.
