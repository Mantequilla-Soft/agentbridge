#!/usr/bin/env bash
# Usage: ./send-dm.sh <agent-name> <message>
set -euo pipefail

AGENT="${1:?Usage: send-dm.sh <agent-name> <message>}"
MESSAGE="${2:?Usage: send-dm.sh <agent-name> <message>}"

agentbridge dm "$AGENT" "$MESSAGE"
