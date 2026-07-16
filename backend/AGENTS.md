# Backend Agent Reference

## Scope

This folder contains the FastAPI backend used for the PM MVP single-container deployment.

## Part 2 contents

- `app/main.py`: FastAPI application entrypoint.
- `static/`: Build output directory for exported Next.js frontend (copied in Docker build).
- `requirements.txt`: Python dependencies installed in Docker via `uv`.

## Runtime contract

- `GET /` serves the exported frontend app.
- `GET /api/health` returns backend health JSON.
- `GET /{path}` serves static frontend files with index fallback for app routes.