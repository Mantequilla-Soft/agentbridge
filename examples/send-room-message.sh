#!/usr/bin/env bash
# Usage: ./send-room-message.sh <room> <message>
set -euo pipefail

ROOM="${1:?Usage: send-room-message.sh <room> <message>}"
MESSAGE="${2:?Usage: send-room-message.sh <room> <message>}"

agentbridge send --room "$ROOM" "$MESSAGE"
