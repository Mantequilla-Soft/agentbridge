from __future__ import annotations

import json
from pathlib import Path

from .config import CURSOR_DIR


def cursor_path(agent_name: str) -> Path:
    return CURSOR_DIR / f"cursor-{agent_name}.json"


def read_cursor(agent_name: str) -> int:
    path = cursor_path(agent_name)
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text())
        return int(data.get("since", 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return 0


def write_cursor(agent_name: str, since: int) -> None:
    path = cursor_path(agent_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"since": since}))
