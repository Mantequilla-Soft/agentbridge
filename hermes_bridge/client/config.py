from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ENV_FILE = Path.home() / ".hermes-bridge" / ".env"
CURSOR_DIR = Path.home() / ".hermes-bridge"


class ClientSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HERMES_", extra="ignore")

    server_url: str
    agent_name: str
    agent_token: str


def load_settings(env_file: Path | None = None) -> ClientSettings:
    """Loads config from (in order of precedence) env vars, then the given/default .env file."""
    if env_file is None:
        env_file = DEFAULT_ENV_FILE if DEFAULT_ENV_FILE.exists() else None
    if env_file is not None:
        return ClientSettings(_env_file=str(env_file))
    return ClientSettings()
