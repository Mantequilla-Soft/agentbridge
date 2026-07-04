#!/usr/bin/env bash
# Implements the "radio" polling protocol: default 5-minute polling, switching
# to 30-second active polling while a conversation is in progress (a message
# ending in "over" means "your turn, I'm waiting"), reverting to default
# ~5 minutes after the last "over" if no reply arrives ("over and out" closes
# it immediately).
#
# This is the ONE process that should call plain `agentbridge inbox` for this
# identity (see ../README.md, "one consuming reader per identity") — do not
# also run a second script that consumes inbox for the same agent.
#
# Meant to be ticked every 30 seconds by radio-poll.timer (see that file —
# plain cron can't go below 1-minute granularity). Safe to tick more or less
# often than that: it self-throttles to the 5-minute default cadence
# internally and only calls the consuming `agentbridge inbox` when actually due.
set -euo pipefail

AGENT_NAME="${HERMES_AGENT_NAME:?Set HERMES_AGENT_NAME (e.g. via EnvironmentFile=%h/.hermes-bridge/.env in the systemd unit)}"
STATE_DIR="$HOME/.hermes-bridge/state"
ACTIVE_FILE="$STATE_DIR/${AGENT_NAME}-active-since"
LAST_POLL_FILE="$STATE_DIR/${AGENT_NAME}-last-poll"
LOG="${HERMES_BRIDGE_LOG:-$HOME/.hermes-bridge/radio-poll.log}"
mkdir -p "$STATE_DIR" "$(dirname "$LOG")"

DEFAULT_INTERVAL=300   # seconds between polls while idle (5 minutes)
ACTIVE_TIMEOUT=315     # revert to default this long after the last "over" (5 min + grace)

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [$AGENT_NAME] $*" >> "$LOG"; }

now=$(date +%s)

is_active=false
if [ -f "$ACTIVE_FILE" ]; then
  active_since=$(cat "$ACTIVE_FILE")
  if [ $((now - active_since)) -lt "$ACTIVE_TIMEOUT" ]; then
    is_active=true
  else
    rm -f "$ACTIVE_FILE"
    log "active mode timed out, reverting to default (5 min) polling"
  fi
fi

last_poll=0
[ -f "$LAST_POLL_FILE" ] && last_poll=$(cat "$LAST_POLL_FILE")

if [ "$is_active" = false ] && [ $((now - last_poll)) -lt "$DEFAULT_INTERVAL" ]; then
  exit 0   # not due yet
fi
echo "$now" > "$LAST_POLL_FILE"

result=$(agentbridge inbox --json)
new_count=$(python3 -c 'import json,sys; print(len(json.load(sys.stdin)["messages"]))' <<< "$result")
[ "$new_count" -eq 0 ] && exit 0

log "${new_count} new message(s)"

last_body=$(python3 -c 'import json,sys; m=json.load(sys.stdin)["messages"]; print(m[-1]["body"] if m else "")' <<< "$result")
normalized=$(printf '%s' "$last_body" | tr '[:upper:]' '[:lower:]' | sed -e 's/[[:space:]]*$//')

if [[ "$normalized" == *"over and out" ]]; then
  rm -f "$ACTIVE_FILE"
  log "conversation closed (over and out)"
elif [[ "$normalized" == *"over" ]]; then
  echo "$now" > "$ACTIVE_FILE"
  log "entering/continuing active mode (over)"
fi

# Hand off $result (JSON) to your agent framework here to actually decide on
# and send a reply, e.g.:
#   printf '%s' "$result" | your-agent-framework-command
