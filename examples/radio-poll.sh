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

# Only inbound (from someone else) messages should drive the active/idle
# state machine. `agentbridge inbox` echoes back the agent's own outgoing
# sends once the cursor passes them, so filtering by sender avoids reacting
# to our own "over"/"over and out" and mis-toggling active mode.
last_body=$(python3 -c '
import json, sys
agent = sys.argv[1]
messages = json.load(sys.stdin)["messages"]
inbound = [m for m in messages if m.get("sender") != agent]
print(inbound[-1]["body"] if inbound else "")
' "$AGENT_NAME" <<< "$result")
# Strip trailing punctuation too (not just whitespace) so "...over?" or
# "...over." still match the plain-suffix check below — a literal string
# match against typed punctuation was silently missing these.
normalized=$(printf '%s' "$last_body" | tr '[:upper:]' '[:lower:]' | sed -E 's/[[:space:][:punct:]]*$//')

if [[ "$normalized" == *"over and out" ]]; then
  rm -f "$ACTIVE_FILE"
  log "conversation closed (over and out)"
elif [[ "$normalized" == *"over" ]]; then
  echo "$now" > "$ACTIVE_FILE"
  log "entering/continuing active mode (over)"
fi

prompt=$(cat <<PROMPTEOF
You are the "${AGENT_NAME}" identity on the hermes-bridge. ${new_count} new
message(s) just arrived in your inbox. This poller already consumed them off
the shared cursor via a consuming \`agentbridge inbox\` call, so do NOT call
plain \`agentbridge inbox\` yourself for these (it would silently swallow the
next real reader's turn) — use \`agentbridge inbox --all --json\` if you need
to re-inspect history non-destructively.

New message(s), oldest first, as JSON:
${result}

Apply the agentbridge-client skill's conversation protocol to decide whether
this warrants a reply (explicit invocation, @mention, [TASK] marker, or a
direct DM to you all count; a stray room message you weren't addressed in
does not). If you reply, send it yourself right now with \`agentbridge dm\`
or \`agentbridge send --room\`, ending with "over" if you expect the other
party to reply back, or "over and out" to close the exchange. If nothing
warrants a reply, just say so briefly — do not invent busywork.
PROMPTEOF
)

reply=$(timeout 180 hermes -z "$prompt" -t terminal --skills agentbridge-client 2>>"$LOG")
log "agent handoff done: ${reply:0:200}"
