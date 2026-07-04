#!/usr/bin/env bash
# Safe to run from cron as often as you like — uses --all, which never
# mutates the shared read cursor. Use this for logging/liveness checks only;
# it must NOT be the thing that drives your agent's actual replies (that's
# agent-turn.sh's job).
set -euo pipefail

LOG="${HERMES_BRIDGE_LOG:-$HOME/.hermes-bridge/heartbeat.log}"
mkdir -p "$(dirname "$LOG")"

agentbridge inbox --all --json | python3 -c '
import json, sys, datetime
data = json.load(sys.stdin)
messages = data["messages"]
latest = messages[-1]["id"] if messages else "none"
ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
print(f"{ts} heartbeat: {len(messages)} total visible message(s), latest id={latest}")
' >> "$LOG"
