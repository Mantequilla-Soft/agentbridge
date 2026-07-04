from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from . import db as db_mod
from .auth import get_conn, get_current_agent
from .schemas import AgentOut, AgentsResponse

router = APIRouter()


@router.get("/v1/agents", response_model=AgentsResponse)
def list_agents(
    _agent: sqlite3.Row = Depends(get_current_agent),
    conn: sqlite3.Connection = Depends(get_conn),
) -> AgentsResponse:
    rows = db_mod.list_agents(conn, active_only=True)
    return AgentsResponse(agents=[AgentOut(name=r["name"], created_at=r["created_at"]) for r in rows])
