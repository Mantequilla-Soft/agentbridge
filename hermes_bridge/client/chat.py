from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .api import BridgeClient
from .state import read_cursor, write_cursor

POLL_INTERVAL_SECONDS = 2.0
HISTORY_LIMIT = 500
HISTORY_SHOWN = 20


@dataclass
class Target:
    kind: str  # "room" or "dm"
    name: str

    def label(self) -> str:
        return f"#{self.name}" if self.kind == "room" else f"@{self.name}"

    def matches(self, message: dict, my_name: str) -> bool:
        if self.kind == "room":
            return message["target_type"] == "room" and message["target"] == self.name
        if message["target_type"] != "dm":
            return False
        return (message["sender"] == my_name and message["target"] == self.name) or (
            message["sender"] == self.name and message["target"] == my_name
        )


def format_message(m: dict) -> str:
    file_note = f" [file: {m['file']['filename']} id={m['file']['id']}]" if m.get("file") else ""
    return f"[{m['id']}] {m['sender']}: {m['body']}{file_note}"


class ChatSession:
    def __init__(self, client: BridgeClient, my_name: str, initial_target: Target | None = None):
        self.client = client
        self.my_name = my_name
        self.target = initial_target or Target("room", "general")
        self._lock = threading.Lock()
        self._seen_ids: set[int] = set()
        self._stop = threading.Event()

    def _current_target(self) -> Target:
        with self._lock:
            return self.target

    def _set_target(self, target: Target) -> None:
        with self._lock:
            self.target = target

    def _show_history(self) -> None:
        # since=0 explicitly: a peek, never touches the persisted read cursor.
        result = self.client.inbox(0, limit=HISTORY_LIMIT)
        target = self._current_target()
        shown = [m for m in result["messages"] if target.matches(m, self.my_name)]
        for m in shown[-HISTORY_SHOWN:]:
            self._seen_ids.add(m["id"])
            print(format_message(m))

    def _poll_loop(self) -> None:
        cursor = read_cursor(self.my_name)
        while not self._stop.is_set():
            try:
                result = self.client.inbox(cursor, limit=200)
            except Exception:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue
            messages = result["messages"]
            if messages:
                cursor = result["next_since"]
                write_cursor(self.my_name, cursor)
                target = self._current_target()
                for m in messages:
                    already_shown = m["id"] in self._seen_ids
                    self._seen_ids.add(m["id"])
                    if not already_shown and target.matches(m, self.my_name):
                        print(f"\n{format_message(m)}\n> ", end="", flush=True)
            self._stop.wait(POLL_INTERVAL_SECONDS)

    def run(self) -> None:
        print(f"Connected as '{self.my_name}'. Now chatting in {self.target.label()}.")
        print("Commands: /agents  /room <name>  /dm <agent>  /quit")
        self._show_history()

        poller = threading.Thread(target=self._poll_loop, daemon=True)
        poller.start()
        try:
            while True:
                try:
                    line = input("> ").strip()
                except EOFError:
                    print()
                    break
                if not line:
                    continue
                if line in ("/quit", "/exit"):
                    break
                if line == "/agents":
                    agents = self.client.agents()["agents"]
                    print("Known agents: " + ", ".join(a["name"] for a in agents))
                    continue
                if line.startswith("/room "):
                    name = line.split(" ", 1)[1].strip()
                    self._set_target(Target("room", name))
                    print(f"Now chatting in #{name}")
                    self._show_history()
                    continue
                if line.startswith("/dm "):
                    name = line.split(" ", 1)[1].strip()
                    self._set_target(Target("dm", name))
                    print(f"Now DMing '{name}'")
                    self._show_history()
                    continue
                target = self._current_target()
                try:
                    sent = self.client.send(target.kind, target.name, line)
                except Exception as e:
                    print(f"(failed to send: {e})")
                    continue
                self._seen_ids.add(sent["id"])
                print(f"(sent, id={sent['id']})")
        finally:
            self._stop.set()
