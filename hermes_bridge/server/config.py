from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HERMES_", extra="ignore")

    data_dir: Path = Path("./data")
    files_dir: Path | None = None
    db_path: Path | None = None
    max_upload_mb: int = 200
    log_level: str = "info"

    @property
    def resolved_files_dir(self) -> Path:
        return self.files_dir or (self.data_dir / "files")

    @property
    def resolved_db_path(self) -> Path:
        return self.db_path or (self.data_dir / "db.sqlite3")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


def get_settings() -> ServerSettings:
    """Not cached: FastAPI dependency overrides / tests need fresh settings per instantiation."""
    return ServerSettings()
