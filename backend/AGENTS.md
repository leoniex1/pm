# Backend Agent Reference

## Scope

This folder contains the FastAPI backend used for the PM MVP single-container deployment.

## Part 2 contents

- `app/main.py`: FastAPI application entrypoint.
- `app/board_store.py`: SQLite SQLAlchemy board persistence layer and seed/bootstrap logic.
- `static/`: Build output directory for exported Next.js frontend (copied in Docker build).
- `requirements.txt`: Python dependencies installed in Docker via `uv`.
- `tests/test_board.py`: board persistence and test-only reset security tests.

## Runtime contract

- `GET /` serves the exported frontend app.
- `GET /api/health` returns backend health JSON.
- `GET /api/board` returns persisted ordered board JSON.
- `PUT /api/board` persists ordered board JSON.
- `GET /{path}` serves static frontend files with index fallback for app routes.

## Test-only behavior

- `POST /api/board/reset` is available only when `ALLOW_TEST_RESET=1` and requires authentication.