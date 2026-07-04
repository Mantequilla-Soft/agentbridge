"""Raw sqlite3 data access. No ORM — three tables, a handful of query shapes."""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS agents (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    token_hash  TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_token_hash ON agents(token_hash);

CREATE TABLE IF NOT EXISTS files (
    id            INTEGER PRIMARY KEY,
    filename      TEXT NOT NULL,
    uploader_id   INTEGER NOT NULL REFERENCES agents(id),
    size_bytes    INTEGER NOT NULL,
    content_type  TEXT,
    storage_path  TEXT NOT NULL,
    sha256        TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY,
    sender_id    INTEGER NOT NULL REFERENCES agents(id),
    target_type  TEXT NOT NULL CHECK (target_type IN ('room','dm')),
    target       TEXT NOT NULL,
    body         TEXT NOT NULL DEFAULT '',
    file_id      INTEGER REFERENCES files(id),
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_target ON messages(target_type, target, id);

CREATE TABLE IF NOT EXISTS receipts (
    message_id  INTEGER NOT NULL REFERENCES messages(id),
    agent_id    INTEGER NOT NULL REFERENCES agents(id),
    seen_at     TEXT NOT NULL,
    PRIMARY KEY (message_id, agent_id)
);

CREATE TABLE IF NOT EXISTS presence (
    agent_id    INTEGER PRIMARY KEY REFERENCES agents(id),
    status      TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

# Fragment shared by inbox lookup and file-access checks: rows visible to :name/:id
_VISIBILITY_SQL = """
    (m.target_type = 'room' OR m.sender_id = :agent_id OR m.target = :agent_name)
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


# --- agents -----------------------------------------------------------------

def create_agent(conn: sqlite3.Connection, name: str) -> tuple[sqlite3.Row, str]:
    token = generate_token()
    cur = conn.execute(
        "INSERT INTO agents (name, token_hash, is_active, created_at) VALUES (?, ?, 1, ?)",
        (name, hash_token(token), now_iso()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM agents WHERE id = ?", (cur.lastrowid,)).fetchone()
    return row, token


def get_agent_by_token_hash(conn: sqlite3.Connection, token_hash: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM agents WHERE token_hash = ?", (token_hash,)).fetchone()


def get_agent_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()


def get_agent_by_id(conn: sqlite3.Connection, agent_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()


def list_agents(conn: sqlite3.Connection, active_only: bool = True) -> list[sqlite3.Row]:
    if active_only:
        return conn.execute(
            "SELECT * FROM agents WHERE is_active = 1 ORDER BY name"
        ).fetchall()
    return conn.execute("SELECT * FROM agents ORDER BY name").fetchall()


def revoke_agent(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute("UPDATE agents SET is_active = 0 WHERE name = ?", (name,))
    conn.commit()
    return cur.rowcount > 0


# --- messages -----------------------------------------------------------------

def insert_message(
    conn: sqlite3.Connection,
    *,
    sender_id: int,
    target_type: str,
    target: str,
    body: str,
    file_id: int | None,
) -> sqlite3.Row:
    cur = conn.execute(
        "INSERT INTO messages (sender_id, target_type, target, body, file_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (sender_id, target_type, target, body, file_id, now_iso()),
    )
    conn.commit()
    return conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()


def get_inbox(
    conn: sqlite3.Connection,
    *,
    agent_id: int,
    agent_name: str,
    since: int,
    limit: int,
) -> list[sqlite3.Row]:
    query = f"""
        SELECT m.* FROM messages m
        WHERE m.id > :since AND {_VISIBILITY_SQL}
        ORDER BY m.id ASC
        LIMIT :limit
    """
    return conn.execute(
        query, {"since": since, "limit": limit, "agent_id": agent_id, "agent_name": agent_name}
    ).fetchall()


def can_access_message(
    conn: sqlite3.Connection, *, agent_id: int, agent_name: str, message_id: int
) -> sqlite3.Row | None:
    query = f"""
        SELECT m.* FROM messages m
        WHERE m.id = :message_id AND {_VISIBILITY_SQL}
    """
    return conn.execute(
        query, {"message_id": message_id, "agent_id": agent_id, "agent_name": agent_name}
    ).fetchone()


# --- receipts -----------------------------------------------------------------

def mark_read(
    conn: sqlite3.Connection, *, agent_id: int, agent_name: str, message_ids: list[int]
) -> int:
    """Record `agent_id` as having read each message id it can actually see. Silently
    ignores ids that don't exist or aren't visible to this agent, rather than erroring —
    a caller passing a stale or foreign id shouldn't blow up the whole batch."""
    if not message_ids:
        return 0
    id_params = {f"id{i}": mid for i, mid in enumerate(message_ids)}
    placeholders = ",".join(f":{k}" for k in id_params)
    query = f"""
        SELECT m.id FROM messages m
        WHERE m.id IN ({placeholders}) AND {_VISIBILITY_SQL}
    """
    params = {**id_params, "agent_id": agent_id, "agent_name": agent_name}
    visible_ids = [row["id"] for row in conn.execute(query, params).fetchall()]
    seen_at = now_iso()
    conn.executemany(
        "INSERT OR IGNORE INTO receipts (message_id, agent_id, seen_at) VALUES (?, ?, ?)",
        [(mid, agent_id, seen_at) for mid in visible_ids],
    )
    conn.commit()
    return len(visible_ids)


def get_receipts(conn: sqlite3.Connection, *, message_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT r.seen_at, a.name AS agent_name FROM receipts r
        JOIN agents a ON a.id = r.agent_id
        WHERE r.message_id = ?
        ORDER BY r.seen_at ASC
        """,
        (message_id,),
    ).fetchall()


# --- presence -----------------------------------------------------------------

def set_presence(conn: sqlite3.Connection, *, agent_id: int, status_value: str) -> sqlite3.Row:
    conn.execute(
        "INSERT INTO presence (agent_id, status, updated_at) VALUES (:agent_id, :status, :updated_at) "
        "ON CONFLICT(agent_id) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at",
        {"agent_id": agent_id, "status": status_value, "updated_at": now_iso()},
    )
    conn.commit()
    return conn.execute("SELECT * FROM presence WHERE agent_id = ?", (agent_id,)).fetchone()


def get_presence(conn: sqlite3.Connection, *, agent_names: list[str]) -> list[sqlite3.Row]:
    """One row per requested name, via LEFT JOIN, so an agent with no presence set yet
    still appears (with status/updated_at NULL) instead of being silently dropped."""
    if not agent_names:
        return []
    placeholders = ",".join("?" * len(agent_names))
    return conn.execute(
        f"""
        SELECT a.name AS agent_name, p.status, p.updated_at
        FROM agents a LEFT JOIN presence p ON p.agent_id = a.id
        WHERE a.name IN ({placeholders})
        """,
        agent_names,
    ).fetchall()


# --- files -----------------------------------------------------------------

def insert_file(
    conn: sqlite3.Connection,
    *,
    filename: str,
    uploader_id: int,
    size_bytes: int,
    content_type: str | None,
    storage_path: str,
    sha256: str | None,
) -> sqlite3.Row:
    cur = conn.execute(
        "INSERT INTO files (filename, uploader_id, size_bytes, content_type, storage_path, sha256, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (filename, uploader_id, size_bytes, content_type, storage_path, sha256, now_iso()),
    )
    conn.commit()
    return conn.execute("SELECT * FROM files WHERE id = ?", (cur.lastrowid,)).fetchone()


def get_file(conn: sqlite3.Connection, file_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()


def can_access_file(conn: sqlite3.Connection, *, agent_id: int, agent_name: str, file_id: int) -> bool:
    """A file is accessible if the requester uploaded it, or can see a message referencing it."""
    file_row = get_file(conn, file_id)
    if file_row is None:
        return False
    if file_row["uploader_id"] == agent_id:
        return True
    query = f"""
        SELECT 1 FROM messages m
        WHERE m.file_id = :file_id AND {_VISIBILITY_SQL}
        LIMIT 1
    """
    row = conn.execute(
        query, {"file_id": file_id, "agent_id": agent_id, "agent_name": agent_name}
    ).fetchone()
    return row is not None
