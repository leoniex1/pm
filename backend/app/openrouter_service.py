from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import httpx

DEFAULT_OPENROUTER_MODEL = "openai/gpt-oss-120b"
OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class OpenRouterConfigurationError(Exception):
    pass


class OpenRouterRequestError(Exception):
    pass


@dataclass(frozen=True)
class OpenRouterConfig:
    api_key: str
    model: str


@dataclass(frozen=True)
class OpenRouterReply:
    model: str
    text: str


def _read_env_file_value(env_file: Path, key: str) -> str | None:
    if not env_file.is_file():
        return None

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        entry_key, entry_value = line.split("=", 1)
        if entry_key.strip() != key:
            continue

        value = entry_value.strip().strip('"').strip("'")
        return value or None

    return None


def _read_setting(name: str, env_file: Path) -> str | None:
    env_value = os.getenv(name)
    if env_value:
        return env_value
    return _read_env_file_value(env_file, name)


def get_openrouter_config(env_file: Path = DEFAULT_ENV_FILE) -> OpenRouterConfig:
    api_key = _read_setting("OPENROUTER_API_KEY", env_file)
    if not api_key:
        raise OpenRouterConfigurationError("OpenRouter API key is not configured")

    model = _read_setting("OPENROUTER_MODEL", env_file) or DEFAULT_OPENROUTER_MODEL
    return OpenRouterConfig(api_key=api_key, model=model)


def query_openrouter(prompt: str, env_file: Path = DEFAULT_ENV_FILE) -> OpenRouterReply:
    config = get_openrouter_config(env_file=env_file)

    payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
    }

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post(
            OPENROUTER_CHAT_COMPLETIONS_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OpenRouterRequestError("OpenRouter request failed") from exc

    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenRouterRequestError("OpenRouter response format was invalid") from exc

    if isinstance(content, list):
        # Handle multimodal-style content arrays by concatenating text fragments.
        text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        content_text = "\n".join(part for part in text_parts if part)
    else:
        content_text = str(content)

    return OpenRouterReply(model=config.model, text=content_text)
