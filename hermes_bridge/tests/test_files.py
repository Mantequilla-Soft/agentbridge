from __future__ import annotations

import hashlib

from .conftest import auth_headers


def test_file_roundtrip(app_client, register, tmp_path):
    headers = auth_headers(register("alice"))
    content = b"hello world " * 100
    src = tmp_path / "test.txt"
    src.write_bytes(content)

    with src.open("rb") as f:
        upload = app_client.post("/v1/files", files={"file": ("test.txt", f, "text/plain")}, headers=headers)
    assert upload.status_code == 201
    meta = upload.json()
    assert meta["size_bytes"] == len(content)
    assert meta["sha256"] == hashlib.sha256(content).hexdigest()

    download = app_client.get(f"/v1/files/{meta['id']}", headers=headers)
    assert download.status_code == 200
    assert download.content == content


def test_file_access_follows_message_visibility(app_client, register, tmp_path):
    alice_headers = auth_headers(register("alice"))
    bob_headers = auth_headers(register("bob"))
    carol_headers = auth_headers(register("carol"))

    src = tmp_path / "secret.txt"
    src.write_bytes(b"top secret mockup")
    with src.open("rb") as f:
        upload = app_client.post("/v1/files", files={"file": ("secret.txt", f)}, headers=alice_headers)
    file_id = upload.json()["id"]

    attach = app_client.post(
        "/v1/messages",
        json={"target_type": "dm", "target": "bob", "body": "here's the file", "file_id": file_id},
        headers=alice_headers,
    )
    assert attach.status_code == 201

    assert app_client.get(f"/v1/files/{file_id}", headers=alice_headers).status_code == 200  # uploader
    assert app_client.get(f"/v1/files/{file_id}", headers=bob_headers).status_code == 200  # DM recipient
    assert app_client.get(f"/v1/files/{file_id}", headers=carol_headers).status_code == 404  # uninvolved


def test_uploader_can_fetch_unattached_file(app_client, register, tmp_path):
    headers = auth_headers(register("alice"))
    src = tmp_path / "draft.txt"
    src.write_bytes(b"not attached to any message yet")
    with src.open("rb") as f:
        upload = app_client.post("/v1/files", files={"file": ("draft.txt", f)}, headers=headers)
    file_id = upload.json()["id"]

    assert app_client.get(f"/v1/files/{file_id}", headers=headers).status_code == 200


def test_room_attachment_visible_to_everyone(app_client, register, tmp_path):
    alice_headers = auth_headers(register("alice"))
    carol_headers = auth_headers(register("carol"))

    src = tmp_path / "public.txt"
    src.write_bytes(b"public deliverable")
    with src.open("rb") as f:
        upload = app_client.post("/v1/files", files={"file": ("public.txt", f)}, headers=alice_headers)
    file_id = upload.json()["id"]

    app_client.post(
        "/v1/messages",
        json={"target_type": "room", "target": "general", "body": "shared with everyone", "file_id": file_id},
        headers=alice_headers,
    )

    assert app_client.get(f"/v1/files/{file_id}", headers=carol_headers).status_code == 200


def test_upload_over_size_limit_rejected(app_client, register, tmp_path, monkeypatch):
    headers = auth_headers(register("alice"))
    monkeypatch.setenv("HERMES_MAX_UPLOAD_MB", "0")
    src = tmp_path / "big.bin"
    src.write_bytes(b"x" * 1000)

    with src.open("rb") as f:
        resp = app_client.post("/v1/files", files={"file": ("big.bin", f)}, headers=headers)
    assert resp.status_code == 413
