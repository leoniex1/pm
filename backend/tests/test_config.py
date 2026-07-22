import pytest

from backend.app.config import (
    DEFAULT_DEVELOPMENT_SESSION_SECRET,
    SessionSecretConfigurationError,
    parse_bool_env,
    resolve_session_secret,
)


def test_development_fallback_secret_is_used_when_unset() -> None:
    assert resolve_session_secret("development", None) == DEFAULT_DEVELOPMENT_SESSION_SECRET


def test_explicit_secret_wins_even_in_development() -> None:
    assert resolve_session_secret("development", "explicit-secret") == "explicit-secret"


def test_non_development_environment_rejects_missing_secret() -> None:
    with pytest.raises(SessionSecretConfigurationError):
        resolve_session_secret("production", None)


def test_non_development_environment_accepts_explicit_secret() -> None:
    assert resolve_session_secret("production", "real-secret") == "real-secret"


@pytest.mark.parametrize("value", ["1", "true", "True", "yes", "YES"])
def test_parse_bool_env_recognizes_true_values(value: str) -> None:
    assert parse_bool_env(value) is True


@pytest.mark.parametrize("value", ["0", "false", "no", "", "garbage"])
def test_parse_bool_env_recognizes_false_values(value: str) -> None:
    assert parse_bool_env(value) is False


def test_parse_bool_env_uses_default_when_unset() -> None:
    assert parse_bool_env(None, default=False) is False
    assert parse_bool_env(None, default=True) is True
