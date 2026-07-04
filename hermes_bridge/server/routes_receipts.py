from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from . import db as db_mod
from .auth import get_conn, get_current_agent
from .schemas import MarkReadResponse, MessageReceiptsResponse, ReceiptOut, ReceiptsRequest

router = APIRouter()


@router.post("/v1/receipts", response_model=MarkReadResponse)
def mark_read(
    payload: ReceiptsRequest,
    agent: sqlite3.Row = Depends(get_current_agent),
    conn: sqlite3.Connection = Depends(get_conn),
) -> MarkReadResponse:
    marked = db_mod.mark_read(
        conn, agent_id=agent["id"], agent_name=agent["name"], message_ids=payload.message_ids
    )
    return MarkReadResponse(marked=marked)


@router.get("/v1/messages/{message_id}/receipts", response_model=MessageReceiptsResponse)
def get_message_receipts(
    message_id: int,
    agent: sqlite3.Row = Depends(get_current_agent),
    conn: sqlite3.Connection = Depends(get_conn),
) -> MessageReceiptsResponse:
    if db_mod.can_access_message(conn, agent_id=agent["id"], agent_name=agent["name"], message_id=message_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown message {message_id}")
    rows = db_mod.get_receipts(conn, message_id=message_id)
    return MessageReceiptsResponse(
        message_id=message_id,
        receipts=[ReceiptOut(agent=r["agent_name"], seen_at=r["seen_at"]) for r in rows],
    )
