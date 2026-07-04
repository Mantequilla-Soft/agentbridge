from __future__ import annotations

from .conftest import auth_headers


def test_send_and_inbox_returns_message_with_correct_cursor(app_client, register):
    headers = auth_headers(register("alice"))

    sent = app_client.post(
        "/v1/messages",
        json={"target_type": "room", "target": "general", "body": "hello"},
        headers=headers,
    )
    assert sent.status_code == 201
    msg = sent.json()
    assert msg["body"] == "hello"
    assert msg["sender"] == "alice"

    inbox = app_client.get("/v1/inbox", params={"since": 0}, headers=headers).json()
    assert len(inbox["messages"]) == 1
    assert inbox["messages"][0]["id"] == msg["id"]
    assert inbox["next_since"] == msg["id"]


def test_cursor_advances_returns_empty_on_repeat(app_client, register):
    headers = auth_headers(register("alice"))
    app_client.post(
        "/v1/messages", json={"target_type": "room", "target": "general", "body": "hi"}, headers=headers
    )
    first = app_client.get("/v1/inbox", params={"since": 0}, headers=headers).json()
    assert len(first["messages"]) == 1

    second = app_client.get("/v1/inbox", params={"since": first["next_since"]}, headers=headers).json()
    assert second["messages"] == []
    assert second["next_since"] == first["next_since"]


def test_dm_isolation(app_client, register):
    alice_headers = auth_headers(register("alice"))
    bob_headers = auth_headers(register("bob"))
    carol_headers = auth_headers(register("carol"))

    resp = app_client.post(
        "/v1/messages", json={"target_type": "dm", "target": "bob", "body": "secret"}, headers=alice_headers
    )
    assert resp.status_code == 201

    bob_inbox = app_client.get("/v1/inbox", headers=bob_headers).json()
    assert any(m["body"] == "secret" for m in bob_inbox["messages"])

    carol_inbox = app_client.get("/v1/inbox", headers=carol_headers).json()
    assert all(m["body"] != "secret" for m in carol_inbox["messages"])


def test_sender_sees_own_sent_messages(app_client, register):
    alice_headers = auth_headers(register("alice"))
    register("bob")

    app_client.post(
        "/v1/messages", json={"target_type": "dm", "target": "bob", "body": "hey bob"}, headers=alice_headers
    )
    alice_inbox = app_client.get("/v1/inbox", headers=alice_headers).json()
    assert any(m["body"] == "hey bob" for m in alice_inbox["messages"])


def test_dm_to_unknown_agent_is_404(app_client, register):
    headers = auth_headers(register("alice"))
    resp = app_client.post(
        "/v1/messages", json={"target_type": "dm", "target": "nobody", "body": "hi"}, headers=headers
    )
    assert resp.status_code == 404


def test_empty_body_without_file_is_rejected(app_client, register):
    headers = auth_headers(register("alice"))
    resp = app_client.post(
        "/v1/messages", json={"target_type": "room", "target": "general", "body": ""}, headers=headers
    )
    assert resp.status_code == 400
