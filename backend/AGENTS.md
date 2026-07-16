# Backend Agent Reference

## Scope

This folder contains the FastAPI backend used for the PM MVP single-container deployment.

## Part 2 contents

- `app/main.py`: FastAPI application entrypoint.
- `app/board_store.py`: SQLite SQLAlchemy board persistence layer and seed/bootstrap logic.
- `static/`: Build output directory for exported Next.js frontend (copied in Docker build).
- `requirements.txt`: Python dependencies installed in Docker via `uv`.
- `tests/test_board.py`: board persistence and test-only reset security tests.

## Data model notes

- `users` table exists with unique username.
- `boards` belong to a user via `boards.user_id`.
- `columns` and `cards` preserve deterministic ordering via `position` with uniqueness constraints.

## Runtime contract

- `GET /` serves the exported frontend app.
- `GET /api/health` returns backend health JSON.
- `GET /api/board` returns persisted ordered board JSON.
- `PUT /api/board` persists ordered board JSON.
- `POST /api/ai/connectivity` sends a simple prompt to OpenRouter and returns model + response text.
- `GET /{path}` serves static frontend files with index fallback for app routes.

## Auth mapping

- Login credentials are validated against `users` in SQLite.
- Session stores `user_id`, and board API calls are scoped to that owner.
- AI connectivity endpoint requires an authenticated session.

## OpenRouter config

- `OPENROUTER_API_KEY` is required.
- `OPENROUTER_MODEL` is optional and defaults to `openai/gpt-oss-120b`.
- Runtime config is resolved from environment variables and falls back to project-root `.env` for local development.

## Test-only behavior

- `POST /api/board/reset` is available only when `ALLOW_TEST_RESET=1` and requires authentication.