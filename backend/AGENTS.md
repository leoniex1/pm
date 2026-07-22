# Backend Agent Reference

## Scope

This folder contains the FastAPI backend used for the PM MVP single-container deployment.

## Part 2 contents

- `app/main.py`: thin FastAPI entrypoint — creates the app, configures middleware, calls
  `init_database()`, includes routers. Does not define any route handlers itself.
- `app/config.py`: environment-driven settings and shared constants (session secret resolution, static
  paths, AI length/rate-limit constants). See "Session/auth configuration" below.
- `app/middleware.py`: `configure_middleware(app)` — session middleware setup.
- `app/dependencies.py`: shared auth helpers (`is_authenticated`, `require_authenticated`,
  `require_session_user_id`) used across routers.
- `app/routers/auth.py`: login/logout/session routes.
- `app/routers/board.py`: board CRUD + test-only reset route.
- `app/routers/ai.py`: AI connectivity/respond routes, request models, and the per-user AI rate limiter.
- `app/routers/health.py`: health check route.
- `app/routers/frontend.py`: `/` and the `/{full_path:path}` catch-all static-file server. Must be
  included last in `main.py` — the catch-all would otherwise shadow every other route.
- `app/board_store.py`: SQLite SQLAlchemy board persistence layer, password hashing, and seed/bootstrap logic.
- `alembic.ini`, `migrations/`: Alembic schema migrations. See "Schema management" below.
- `static/`: Build output directory for exported Next.js frontend (copied in Docker build).
- `requirements.txt`: Python dependencies installed in Docker via `uv`.
- `requirements-dev.txt`: `requirements.txt` plus `pytest`, for running the test suite.
- `tests/test_board.py`: board persistence, referential-integrity validation, and test-only reset security tests.
- `tests/test_password_security.py`: password hashing/verification tests.
- `tests/test_schema_migrations.py`: migration adoption/non-destructiveness tests.
- `tests/test_config.py`: session-secret resolution and boolean-env-parsing tests.
- `tests/test_app_structure.py`: route registration/ordering and router-separation tests.
- `tests/conftest.py`: autouse fixture resetting the AI rate-limit state between tests.

## Data model notes

- `users` table exists with unique username. `password_hash` is a bcrypt hash, never plaintext.
- `boards` belong to a user via `boards.user_id`.
- `columns` and `cards` preserve deterministic ordering via `position` with uniqueness constraints.
  `columns.id`/`cards.id` are string primary keys unique across the whole table (not per-board) — the
  initial seed data for any user beyond the first is given ids with a `-u<user_id>` suffix to avoid
  colliding with an existing board's ids (see `board_store._seed_board_data_for_user`).
- `BoardData` (the read/write JSON model) validates referential integrity on construction: no duplicate
  column ids, no duplicate/missing card references, no orphaned card entries. This applies automatically
  to `PUT /api/board`.

## Schema management

- Schema is managed via Alembic (`alembic.ini`, `migrations/`), not `create_all`/`drop_all` on the
  normal startup path. `board_store._ensure_schema()` never drops existing tables or data:
  - Brand-new database: migrated to head.
  - Database already on Alembic: any pending migrations are applied.
  - Database created before Alembic was adopted (tables exist, no `alembic_version` table): stamped to
    the initial revision in place, since `migrations/versions/0001_initial_schema.py` is defined to
    exactly match the pre-Alembic schema.
- To add a schema change: write a new Alembic revision under `migrations/versions/`. Do not reintroduce
  destructive drop-and-recreate logic on the startup path — that was a critical finding (see
  `docs/code_reviews.md`, F1) precisely because `backend/data` is a persistent volume in the Docker setup.
- `reset_database()` remains a **test-only** full wipe-and-reseed (`drop_all`/`create_all`); it is never
  called from the normal startup path.

## Runtime contract

- `GET /` serves the exported frontend app.
- `GET /api/health` returns backend health JSON.
- `GET /api/board` returns persisted ordered board JSON.
- `PUT /api/board` persists ordered board JSON; rejects payloads that fail referential-integrity
  validation with a 422 (see "Data model notes").
- `POST /api/ai/connectivity` sends a simple prompt to OpenRouter and returns model + response text.
  Rate-limited per user; prompt length capped at 4000 chars.
- `POST /api/ai/respond` sends board-aware prompt context to OpenRouter, validates structured output, and applies allowed operations atomically. Rate-limited per user; message length capped at 4000 chars.
- `GET /{path}` serves static frontend files with index fallback for app routes.

## Auth mapping

- Login credentials are validated against `users` in SQLite, with bcrypt hash verification
  (`board_store._verify_password`) — passwords are never stored or compared as plaintext.
- Session stores `user_id`, and board API calls are scoped to that owner.
- AI connectivity endpoint requires an authenticated session.
- No CORS middleware is configured: the frontend is always served same-origin (see
  `frontend/AGENTS.md` for the local dev/e2e workflow that keeps this true outside Docker too).

## Session/auth configuration

- `SESSION_SECRET` (env var): `config.resolve_session_secret(environment, secret)` only falls back to a
  hardcoded development secret when `ENVIRONMENT` is `"development"` (the default, so local/test
  behavior is unchanged with no env vars set). Any other `ENVIRONMENT` value with no `SESSION_SECRET`
  raises `SessionSecretConfigurationError` at startup — refuses to run with an insecure default outside
  development.
- `SESSION_HTTPS_ONLY` (env var, default `false`): whether the session cookie is HTTPS-only. Defaults to
  `false` because the local/Docker MVP has no TLS termination; set to `true` behind TLS.

## OpenRouter config

- `OPENROUTER_API_KEY` is required.
- `OPENROUTER_MODEL` is optional and defaults to `openai/gpt-oss-120b`.
- Runtime config is resolved from environment variables and falls back to project-root `.env` for local development.

## Part 9 approval gate

- Structured output contract proposal is documented in `docs/AI_STRUCTURED_OUTPUT_SCHEMA.md`.
- Operations must include unique `id` fields for auditing/debugging.
- Prompt contract includes exact required fields for each allowed operation and complete JSON examples.
- Nonexistent entity requests should prefer Option A no-op behavior (`operations: []`) with no mutation.

## Test-only behavior

- `POST /api/board/reset` is available only when `ALLOW_TEST_RESET=1` and requires authentication.