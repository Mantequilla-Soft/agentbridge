from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from . import db as db_mod
from .auth import get_conn, get_current_agent
from .config import get_settings
from .schemas import PresenceOut, PresenceResponse, PresenceSet

router = APIRouter()


def _is_stale(updated_at: str | None, ttl_seconds: int) -> bool:
    if updated_at is None:
        return True
    seen = datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - seen).total_seconds() > ttl_seconds


@router.put("/v1/presence", response_model=PresenceOut)
def set_presence(
    payload: PresenceSet,
    agent: sqlite3.Row = Depends(get_current_agent),
    conn: sqlite3.Connection = Depends(get_conn),
) -> PresenceOut:
    row = db_mod.set_presence(conn, agent_id=agent["id"], status_value=payload.status)
    return PresenceOut(agent=agent["name"], status=row["status"], updated_at=row["updated_at"], stale=False)


@router.get("/v1/presence", response_model=PresenceResponse)
def get_presence(
    agents: str = Query(..., description="Comma-separated agent names"),
    _agent: sqlite3.Row = Depends(get_current_agent),
    conn: sqlite3.Connection = Depends(get_conn),
) -> PresenceResponse:
    names = [n.strip() for n in agents.split(",") if n.strip()]
    rows = db_mod.get_presence(conn, agent_names=names)
    ttl = get_settings().presence_ttl_seconds
    return PresenceResponse(
        presence=[
            PresenceOut(
                agent=r["agent_name"],
                status=r["status"],
                updated_at=r["updated_at"],
                stale=_is_stale(r["updated_at"], ttl),
            )
            for r in rows
        ]
    )
