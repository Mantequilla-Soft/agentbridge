from __future__ import annotations

from .conftest import auth_headers


def test_missing_token_is_401(app_client):
    resp = app_client.get("/v1/inbox")
    assert resp.status_code == 401


def test_garbage_token_is_401(app_client):
    resp = app_client.get("/v1/inbox", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_revoked_agent_is_403(app_client, register, revoke):
    headers = auth_headers(register("alice"))
    revoke("alice")
    resp = app_client.get("/v1/inbox", headers=headers)
    assert resp.status_code == 403


def test_health_requires_no_auth(app_client):
    resp = app_client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
