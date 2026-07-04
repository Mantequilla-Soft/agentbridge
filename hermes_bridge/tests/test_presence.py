from __future__ import annotations

from .conftest import auth_headers


def test_set_and_get_presence(app_client, register):
    alice_headers = auth_headers(register("alice"))
    bob_headers = auth_headers(register("bob"))

    set_resp = app_client.put("/v1/presence", json={"status": "thinking"}, headers=alice_headers)
    assert set_resp.status_code == 200
    assert set_resp.json()["status"] == "thinking"

    got = app_client.get("/v1/presence", params={"agents": "alice"}, headers=bob_headers).json()
    assert len(got["presence"]) == 1
    assert got["presence"][0]["agent"] == "alice"
    assert got["presence"][0]["status"] == "thinking"
    assert got["presence"][0]["stale"] is False


def test_presence_for_agent_with_no_status_is_none_and_stale(app_client, register):
    register("alice")
    bob_headers = auth_headers(register("bob"))

    got = app_client.get("/v1/presence", params={"agents": "alice"}, headers=bob_headers).json()
    assert got["presence"][0]["status"] is None
    assert got["presence"][0]["stale"] is True


def test_presence_older_than_ttl_is_stale(app_client, register, monkeypatch):
    alice_headers = auth_headers(register("alice"))
    bob_headers = auth_headers(register("bob"))

    app_client.put("/v1/presence", json={"status": "thinking"}, headers=alice_headers)

    monkeypatch.setenv("HERMES_PRESENCE_TTL_SECONDS", "-1")
    got = app_client.get("/v1/presence", params={"agents": "alice"}, headers=bob_headers).json()
    assert got["presence"][0]["status"] == "thinking"
    assert got["presence"][0]["stale"] is True


def test_get_presence_omits_unknown_agent_names(app_client, register):
    headers = auth_headers(register("alice"))
    got = app_client.get("/v1/presence", params={"agents": "alice,nobody"}, headers=headers).json()
    assert [p["agent"] for p in got["presence"]] == ["alice"]


def test_set_presence_overwrites_previous_status(app_client, register):
    alice_headers = auth_headers(register("alice"))
    bob_headers = auth_headers(register("bob"))

    app_client.put("/v1/presence", json={"status": "thinking"}, headers=alice_headers)
    app_client.put("/v1/presence", json={"status": "idle"}, headers=alice_headers)

    got = app_client.get("/v1/presence", params={"agents": "alice"}, headers=bob_headers).json()
    assert got["presence"][0]["status"] == "idle"
