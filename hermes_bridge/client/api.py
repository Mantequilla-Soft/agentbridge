from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx

from .config import ClientSettings


class BridgeError(Exception):
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class AuthError(BridgeError):
    def __init__(self, message: str = "authentication failed"):
        super().__init__(message, exit_code=2)


class NotFoundError(BridgeError):
    def __init__(self, message: str = "not found"):
        super().__init__(message, exit_code=3)


def _error_detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        detail = data.get("detail")
        if detail:
            return str(detail)
    except Exception:
        pass
    return resp.text or f"HTTP {resp.status_code}"


def _parse_filename(content_disposition: str | None) -> str | None:
    if not content_disposition:
        return None
    match = re.search(r'filename="?([^";]+)"?', content_disposition)
    return match.group(1) if match else None


class BridgeClient:
    def __init__(self, settings: ClientSettings, timeout: float = 30.0):
        self.settings = settings
        self._client = httpx.Client(
            base_url=settings.server_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": f"Bearer {settings.agent_token}"},
        )

    def __enter__(self) -> "BridgeClient":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _handle(self, resp: httpx.Response) -> httpx.Response:
        if resp.status_code in (401, 403):
            raise AuthError(_error_detail(resp))
        if resp.status_code == 404:
            raise NotFoundError(_error_detail(resp))
        if resp.status_code >= 400:
            raise BridgeError(_error_detail(resp), exit_code=1)
        return resp

    def health(self) -> dict:
        return self._handle(self._client.get("/v1/health")).json()

    def send(self, target_type: str, target: str, body: str, file_id: int | None = None) -> dict:
        payload = {"target_type": target_type, "target": target, "body": body, "file_id": file_id}
        return self._handle(self._client.post("/v1/messages", json=payload)).json()

    def inbox(self, since: int, limit: int = 100) -> dict:
        params = {"since": since, "limit": limit}
        return self._handle(self._client.get("/v1/inbox", params=params)).json()

    def agents(self) -> dict:
        return self._handle(self._client.get("/v1/agents")).json()

    def mark_read(self, message_ids: list[int]) -> dict:
        return self._handle(self._client.post("/v1/receipts", json={"message_ids": message_ids})).json()

    def message_receipts(self, message_id: int) -> dict:
        return self._handle(self._client.get(f"/v1/messages/{message_id}/receipts")).json()

    def set_presence(self, status_value: str) -> dict:
        return self._handle(self._client.put("/v1/presence", json={"status": status_value})).json()

    def get_presence(self, agent_names: list[str]) -> dict:
        params = {"agents": ",".join(agent_names)}
        return self._handle(self._client.get("/v1/presence", params=params)).json()

    def upload(self, path: Path) -> dict:
        with path.open("rb") as f:
            resp = self._client.post("/v1/files", files={"file": (path.name, f)})
        return self._handle(resp).json()

    def download(self, file_id: int) -> tuple[bytes, str]:
        resp = self._handle(self._client.get(f"/v1/files/{file_id}"))
        filename = _parse_filename(resp.headers.get("content-disposition")) or f"file-{file_id}"
        return resp.content, filename
