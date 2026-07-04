from __future__ import annotations

import sqlite3
from typing import Iterator

from fastapi import Depends, Header, HTTPException, status

from . import db as db_mod
from .config import get_settings


def get_conn() -> Iterator[sqlite3.Connection]:
    settings = get_settings()
    conn = db_mod.connect(settings.resolved_db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_current_agent(
    authorization: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_conn),
) -> sqlite3.Row:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    agent = db_mod.get_agent_by_token_hash(conn, db_mod.hash_token(token))
    if agent is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    if not agent["is_active"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Agent has been revoked")
    return agent
