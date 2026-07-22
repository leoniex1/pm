# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A single-user (MVP) Project Management web app: a Kanban board with an AI chat sidebar that can
create/edit/move cards. NextJS frontend + Python FastAPI backend, packaged into one Docker container
(FastAPI serves the statically-exported NextJS site at `/` as well as the API). SQLite is the database.
AI calls go through OpenRouter (`openai/gpt-oss-120b` by default).

Read `AGENTS.md` (root) for business requirements/decisions, `docs/PLAN.md` for the phased execution
plan/status, `docs/DATABASE_DESIGN.md` for the DB schema, `docs/AI_STRUCTURED_OUTPUT_SCHEMA.md` for
the AI structured-output contract, and `docs/code_reviews.md` for the code review history and
remediation record. Folder-level `AGENTS.md` files (`backend/AGENTS.md`, `frontend/AGENTS.md`,
`scripts/AGENTS.md`) contain architecture/reference notes for that folder — check them before diving
into that area.

## Commands

### Backend (run from repo root — imports are rooted at `backend.app.*`)

```bash
pip install -r backend/requirements-dev.txt   # base requirements + pytest
pytest backend/tests                     # all backend tests
pytest backend/tests/test_board.py       # single file
pytest backend/tests/test_board.py::test_seeded_board_available_after_login  # single test
```

Tests must be run from the repository root (not `backend/`) because test modules import via
`backend.app.board_store`, `backend.app.main`, etc. Point `DATABASE_URL` at a scratch SQLite file before
running tests/experiments locally if you want to avoid touching `backend/data/kanban.db`.

### Frontend (run from `frontend/`)

```bash
npm install
npm run dev          # Next.js dev server only — UI iteration, no backend behind it (see below)
npm run dev:full      # builds the frontend and serves it through the real backend on a scratch DB
npm run build        # production build (also produces the static export used by Docker)
npm run lint
npm run test:unit    # vitest
npm run test:e2e     # builds + serves the full app on a scratch DB, runs Playwright, tears down
npm run test:e2e:raw # playwright test only, against whatever E2E_BASE_URL already points at
npm run test:all     # unit + e2e
```

`npm run dev` only runs the Next.js dev server — every frontend fetch call uses a relative path, and
there is no backend on port 3000, so anything that hits `/api/*` (including the login/auth redirect)
will not work in that mode. It's fine for pure UI/styling iteration. For anything that needs the API,
use `npm run dev:full` (manual local full-stack testing) or `npm run test:e2e` (automated). Both scripts
live in `frontend/scripts/` (`full-stack.mjs`, `e2e.mjs`, `serve.mjs`) and both build the frontend, copy
it into `backend/static/`, and run the real FastAPI backend on a scratch database in the OS temp
directory — never `backend/data/kanban.db`. Setting `E2E_BASE_URL` before running `npm run test:e2e`
skips all of that and runs Playwright directly against whatever URL you provide instead (e.g. a Docker
container already running via `scripts/start-windows.ps1`).

### Docker (single container, run from repo root)

```powershell
scripts/start-windows.ps1   # build image `pm-mvp`, run on :8000, mounts backend/data, uses .env
scripts/stop-windows.ps1
```

Equivalent `start-linux.sh`/`start-mac.sh` and `stop-linux.sh`/`stop-mac.sh` exist for other OSes.
`OPENROUTER_API_KEY` (required) and `OPENROUTER_MODEL` (optional, default `openai/gpt-oss-120b`) are
read from the project-root `.env` file / environment.

## Architecture

### Backend package structure

`backend/app/main.py` is a thin FastAPI entrypoint only: it creates the `FastAPI` app, calls
`configure_middleware(app)`, calls `init_database()`, and includes the routers below — nothing else.
Concerns are split into:

- `config.py` — environment-driven settings and shared constants (session secret resolution, static
  file paths, AI length/rate-limit constants, `LOGIN_PATH`/`FRONTEND_PUBLIC_PATHS`). See "Auth and
  session config" below for the security-relevant part.
- `middleware.py` — `configure_middleware(app)`, wires up `SessionMiddleware` from `config`.
- `dependencies.py` — `is_authenticated`/`require_authenticated`/`require_session_user_id`, shared
  across every router that needs auth.
- `routers/auth.py` — `/api/auth/login`, `/logout`, `/session`.
- `routers/board.py` — `GET`/`PUT /api/board`, `POST /api/board/reset`.
- `routers/ai.py` — `/api/ai/connectivity`, `/api/ai/respond`, plus the AI request models and the
  per-user rate limiter (`_enforce_ai_rate_limit`, `_ai_request_log`).
- `routers/health.py` — `GET /api/health`.
- `routers/frontend.py` — `GET /` and the `GET /{full_path:path}` catch-all static-file server.

**Router registration order matters**: `frontend.router` (containing the catch-all) must always be
included *last* in `main.py`, or it would shadow every `/api/*` route registered after it. Within
`frontend.py` itself, `/` must stay declared before the catch-all for the same reason.

### Auth and session config

- Auth is a server-side cookie session (`SessionMiddleware`), hardcoded credentials `user`/`password`
  for the MVP. There is no JWT/localStorage-based auth guard — session state is authoritative. Passwords
  are hashed with `bcrypt` (`board_store._hash_password`/`_verify_password`) — never stored or compared
  in plaintext.
- `SESSION_SECRET`: read from the environment; `config.resolve_session_secret(environment, secret)` only
  falls back to a hardcoded development secret when `ENVIRONMENT` is `"development"` (the default) — any
  other `ENVIRONMENT` value with no `SESSION_SECRET` set raises `SessionSecretConfigurationError` at
  startup rather than silently running with an insecure default.
- `SESSION_HTTPS_ONLY` (env var, default `false`): cookies aren't HTTPS-only by default because the
  local/Docker MVP has no TLS termination in front of it; set `SESSION_HTTPS_ONLY=true` behind TLS.
- Every board/AI route requires an authenticated session and resolves `user_id` from the session, not
  from client-supplied data.
- The catch-all `GET /{full_path:path}` route serves the exported frontend, redirecting to `/login` for
  unauthenticated requests to non-public paths, with an allowlist for public paths (`/login`,
  `/favicon.ico`, `/robots.txt`, `_next/*` assets).
- No CORS middleware: the frontend is always served same-origin (see the frontend commands above), and
  every frontend fetch call uses a relative path, so no cross-origin request is ever issued.
- `/api/ai/respond` and `/api/ai/connectivity` are rate-limited per authenticated user (in-memory
  sliding window, `routers/ai.py`'s `_enforce_ai_rate_limit` — see `_AI_RATE_LIMIT_MAX_REQUESTS`/
  `_AI_RATE_LIMIT_WINDOW_SECONDS`, sourced from `config.py`). This is process-local, which is fine for
  the current single-instance local MVP.

### Board persistence (`backend/app/board_store.py`)

- Normalized SQLAlchemy schema: `users` -> `boards` -> `columns` -> `cards`, cascading deletes, with
  `position` integer columns giving deterministic ordering (unique per parent scope: `(board_id,
  position)` for columns, `(column_id, position)` for cards). Note `columns.id`/`cards.id` are string
  primary keys unique across the *whole table*, not scoped per board.
- The JSON API shape (`BoardData`: `columns: ColumnData[]` + `cards: dict[id, CardData]`, where each
  column holds an ordered `cardIds` list) is intentionally denormalized/order-based — it does not mirror
  the DB row shape. `get_board` reconstructs this shape from position-ordered DB rows; `save_board` does
  a full delete-and-reinsert of a user's columns/cards on every write, deriving `position` from array
  order. There is no partial/diffed update — every board write replaces the whole columns/cards set for
  that user's board. `BoardData` has a `model_validator` enforcing referential integrity (no duplicate
  column/card ids, no cardIds referencing a missing card, no orphaned card entries) — this runs on every
  `PUT /api/board` automatically and rejects malformed payloads with a 422 instead of silently dropping
  data or crashing.
- MVP is one board per user; multi-board support is schema-ready (`boards.user_id` + unique
  `(user_id, title)`) and every user (not just the hardcoded `user` account) gets a populated seeded
  board on first access (`_ensure_board_for_user`/`_seed_board_data_for_user`).
- **Schema management uses Alembic** (`backend/alembic.ini`, `backend/migrations/`), not
  `create_all`/`drop_all`. `board_store._ensure_schema()` never drops existing tables: a brand-new
  database is migrated to head; a database already on Alembic gets any pending migrations; a database
  created before Alembic was adopted (tables exist, no `alembic_version` row) is `stamp`ed to the initial
  revision in place, since that migration is defined to exactly match the pre-Alembic schema. Add future
  schema changes as new Alembic revisions under `backend/migrations/versions/` — never reintroduce
  drop-and-recreate logic on the normal startup path.
- `reset_database()` is a **test-only** full wipe-and-reseed (still uses `drop_all`/`create_all`
  directly) — it is never called from the normal startup path, only from test fixtures and from
  `POST /api/board/reset`, which itself only works when `ALLOW_TEST_RESET=1`.

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
  resulting board is persisted in one transaction (`routers/ai.py` wraps `save_board(..., commit=False)`
  in `session.begin()`). A validation failure anywhere aborts the entire batch — operations are all-or-
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
  `routers/ai.py` (500 vs 502).

### Frontend (`frontend/src`)

- `KanbanBoard` is the single state container: it owns board state (fetched via `GET /api/board`,
  persisted via `PUT /api/board`), drag/drop orchestration (`@dnd-kit`), and wires the AI sidebar's send
  handler to trigger a board reload after AI-driven mutations.
- Board shape mirrors the backend JSON contract exactly: `columns: Column[]` with ordered `cardIds`,
  plus `cards: Record<string, Card>` keyed by id. `moveCard` in `src/lib/kanban.ts` is the single source
  of truth for reorder/move logic (intra-column reorder, inter-column move, drop-onto-column-append) and
  is unit-tested independently of the DOM. `createId` (also in `kanban.ts`) uses `crypto.randomUUID()`.
- The login page (`src/app/login/page.tsx`) starts with empty username/password fields — no prefilled
  credentials.
- `AiChatSidebar` keeps chat history in memory only for the current page session (no persisted
  transcript) and calls `POST /api/ai/respond` with `{ message, history }`; a returned board triggers an
  immediate reload in `KanbanBoard`.
- All API calls are sent with credentials (cookie session); there is no client-side auth token.
- `persistBoard` in `KanbanBoard.tsx` applies the optimistic update locally, then awaits the `PUT`
  response: on a non-OK response or a network error it reverts to the previous board state and shows a
  dismissible error banner (`data-testid="board-save-error"`) rather than silently diverging from what's
  actually persisted.
- Color tokens live in `src/app/globals.css` — keep changes aligned with the palette in the root
  `AGENTS.md` (accent yellow `#ecad0a`, blue `#209dd7`, purple `#753991`, dark navy `#032147`, gray
  `#888888`).

## Coding standards (from root `AGENTS.md`)

- Use latest stable library versions and idiomatic current approaches.
- Keep it simple: no over-engineering, no unnecessary defensive programming, no speculative features.
- No emojis, anywhere, ever.
- When debugging, find the root cause before applying a fix — do not guess-and-check.
