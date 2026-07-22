"""Application configuration: environment-driven settings and shared constants.

Kept as plain module-level values (not a settings class) to match the rest of
this MVP's style — see board_store._database_url and openrouter_service for
the same "env var, with a documented local-only fallback" pattern.
"""
from __future__ import annotations

import os
from pathlib import Path

_TRUE_VALUES = {"1", "true", "yes"}


class SessionSecretConfigurationError(RuntimeError):
    pass


# Only ever used when ENVIRONMENT is "development" (the default). Never used
# as a silent fallback outside development — see resolve_session_secret.
DEFAULT_DEVELOPMENT_SESSION_SECRET = "pm-mvp-dev-session-secret"


def resolve_session_secret(environment: str, session_secret: str | None) -> str:
    if session_secret:
        return session_secret
    if environment == "development":
        return DEFAULT_DEVELOPMENT_SESSION_SECRET
    raise SessionSecretConfigurationError(
        "SESSION_SECRET must be set via environment variable when ENVIRONMENT "
        "is not 'development'. Refusing to start with an insecure default secret."
    )


def parse_bool_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
SESSION_SECRET = resolve_session_secret(ENVIRONMENT, os.getenv("SESSION_SECRET"))

# Cookies are not sent over HTTPS-only by default because the local/Docker
# MVP deployment has no TLS termination in front of it. Set
# SESSION_HTTPS_ONLY=true when this is deployed behind TLS.
SESSION_HTTPS_ONLY = parse_bool_env(os.getenv("SESSION_HTTPS_ONLY"), default=False)


def allow_test_reset() -> bool:
    # Read live on every call (not cached at import time) so tests can
    # toggle ALLOW_TEST_RESET via monkeypatch.setenv within a running process.
    return os.getenv("ALLOW_TEST_RESET", "0") == "1"

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = _BACKEND_ROOT / "static"
STATIC_INDEX = STATIC_DIR / "index.html"

LOGIN_PATH = "/login"
FRONTEND_PUBLIC_PATHS = {
    LOGIN_PATH,
    "/favicon.ico",
    "/robots.txt",
}

AI_MESSAGE_MAX_LENGTH = 4000
AI_RATE_LIMIT_WINDOW_SECONDS = 60
AI_RATE_LIMIT_MAX_REQUESTS = 20
