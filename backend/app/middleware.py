from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from backend.app import config


def configure_middleware(app: FastAPI) -> None:
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.SESSION_SECRET,
        same_site="lax",
        https_only=config.SESSION_HTTPS_ONLY,
    )

    # No CORS middleware: the frontend is always served same-origin (either
    # the static export served by this backend, or the FastAPI-served build
    # used for local full-stack development/e2e — see scripts/serve.mjs).
    # Every fetch call in the frontend uses a relative path, so no
    # cross-origin request is ever issued and no CORS configuration is needed.
