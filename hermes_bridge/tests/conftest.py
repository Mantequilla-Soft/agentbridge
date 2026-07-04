from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hermes_bridge.server import db as db_mod
from hermes_bridge.server.config import get_settings
from hermes_bridge.server.main import create_app


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HERMES_DB_PATH", raising=False)
    monkeypatch.delenv("HERMES_FILES_DIR", raising=False)
    monkeypatch.delenv("HERMES_MAX_UPLOAD_MB", raising=False)
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def register(app_client):
    """Registers an agent directly against the test DB (bypassing HTTP, mirrors the admin CLI path)."""

    def _register(name: str) -> str:
        settings = get_settings()
        conn = db_mod.connect(settings.resolved_db_path)
        try:
            _row, token = db_mod.create_agent(conn, name)
            return token
        finally:
            conn.close()

    return _register


@pytest.fixture
def revoke():
    def _revoke(name: str) -> None:
        settings = get_settings()
        conn = db_mod.connect(settings.resolved_db_path)
        try:
            db_mod.revoke_agent(conn, name)
        finally:
            conn.close()

    return _revoke


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
