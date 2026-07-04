from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from . import db as db_mod
from .auth import get_conn, get_current_agent
from .schemas import FileOut, InboxResponse, MessageCreate, MessageOut

router = APIRouter()

MAX_BODY_BYTES = 200_000


def _serialize_message(conn: sqlite3.Connection, row: sqlite3.Row) -> MessageOut:
    sender = db_mod.get_agent_by_id(conn, row["sender_id"])
    file_out = None
    if row["file_id"] is not None:
        file_row = db_mod.get_file(conn, row["file_id"])
        if file_row is not None:
            file_out = FileOut(
                id=file_row["id"],
                filename=file_row["filename"],
                size_bytes=file_row["size_bytes"],
                content_type=file_row["content_type"],
                sha256=file_row["sha256"],
                created_at=file_row["created_at"],
            )
    return MessageOut(
        id=row["id"],
        sender=sender["name"] if sender else "unknown",
        target_type=row["target_type"],
        target=row["target"],
        body=row["body"],
        file_id=row["file_id"],
        file=file_out,
        created_at=row["created_at"],
    )


@router.post("/v1/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    payload: MessageCreate,
    agent: sqlite3.Row = Depends(get_current_agent),
    conn: sqlite3.Connection = Depends(get_conn),
) -> MessageOut:
    body = payload.body or ""
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"body exceeds max length of {MAX_BODY_BYTES} bytes")
    if not body and payload.file_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "body must be non-empty unless file_id is set")

    if payload.target_type == "dm":
        target_agent = db_mod.get_agent_by_name(conn, payload.target)
        if target_agent is None or not target_agent["is_active"]:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown agent '{payload.target}'")

    if payload.file_id is not None and db_mod.get_file(conn, payload.file_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown file_id {payload.file_id}")

    row = db_mod.insert_message(
        conn,
        sender_id=agent["id"],
        target_type=payload.target_type,
        target=payload.target,
        body=body,
        file_id=payload.file_id,
    )
    return _serialize_message(conn, row)


@router.get("/v1/inbox", response_model=InboxResponse)
def get_inbox(
    since: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    agent: sqlite3.Row = Depends(get_current_agent),
    conn: sqlite3.Connection = Depends(get_conn),
) -> InboxResponse:
    rows = db_mod.get_inbox(conn, agent_id=agent["id"], agent_name=agent["name"], since=since, limit=limit)
    messages = [_serialize_message(conn, r) for r in rows]
    next_since = messages[-1].id if messages else since
    return InboxResponse(messages=messages, next_since=next_since)
