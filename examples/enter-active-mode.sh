#!/usr/bin/env bash
# Call this right after your agent sends a message it expects a reply to
# (e.g. right after send-dm.sh), so radio-poll.sh switches to active
# (30-second) polling immediately instead of waiting for the next
# default-mode (5-minute) tick.
set -euo pipefail

AGENT_NAME="${HERMES_AGENT_NAME:?Set HERMES_AGENT_NAME first}"
STATE_DIR="$HOME/.hermes-bridge/state"
mkdir -p "$STATE_DIR"
date +%s > "$STATE_DIR/${AGENT_NAME}-active-since"
