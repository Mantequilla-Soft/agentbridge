from __future__ import annotations

from .conftest import auth_headers


def test_mark_read_and_query_receipts(app_client, register):
    alice_headers = auth_headers(register("alice"))
    bob_headers = auth_headers(register("bob"))

    sent = app_client.post(
        "/v1/messages", json={"target_type": "dm", "target": "bob", "body": "hi"}, headers=alice_headers
    ).json()

    empty = app_client.get(f"/v1/messages/{sent['id']}/receipts", headers=alice_headers).json()
    assert empty["receipts"] == []

    mark = app_client.post("/v1/receipts", json={"message_ids": [sent["id"]]}, headers=bob_headers).json()
    assert mark["marked"] == 1

    receipts = app_client.get(f"/v1/messages/{sent['id']}/receipts", headers=alice_headers).json()
    assert len(receipts["receipts"]) == 1
    assert receipts["receipts"][0]["agent"] == "bob"


def test_mark_read_ignores_invisible_messages(app_client, register):
    alice_headers = auth_headers(register("alice"))
    register("bob")
    carol_headers = auth_headers(register("carol"))

    sent = app_client.post(
        "/v1/messages", json={"target_type": "dm", "target": "bob", "body": "secret"}, headers=alice_headers
    ).json()

    # carol can't see alice->bob's DM, so marking it read should be a silent no-op
    mark = app_client.post("/v1/receipts", json={"message_ids": [sent["id"]]}, headers=carol_headers).json()
    assert mark["marked"] == 0

    receipts = app_client.get(f"/v1/messages/{sent['id']}/receipts", headers=alice_headers).json()
    assert receipts["receipts"] == []


def test_receipts_for_unknown_message_is_404(app_client, register):
    headers = auth_headers(register("alice"))
    resp = app_client.get("/v1/messages/999999/receipts", headers=headers)
    assert resp.status_code == 404


def test_receipts_gated_by_message_visibility(app_client, register):
    alice_headers = auth_headers(register("alice"))
    register("bob")
    carol_headers = auth_headers(register("carol"))

    sent = app_client.post(
        "/v1/messages", json={"target_type": "dm", "target": "bob", "body": "secret"}, headers=alice_headers
    ).json()

    resp = app_client.get(f"/v1/messages/{sent['id']}/receipts", headers=carol_headers)
    assert resp.status_code == 404
