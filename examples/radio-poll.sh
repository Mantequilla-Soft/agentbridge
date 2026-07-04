#!/usr/bin/env bash
# Ticks every 5 seconds (via radio-poll.timer — plain cron can't go below
# 1-minute granularity) and checks the inbox every single tick, no idle
# backoff. On new mail, hands off to the agent's own reasoning to decide
# whether to reply and actually send that reply.
#
# This is the ONE process that should call plain `agentbridge inbox` for this
# identity (see ../README.md, "one consuming reader per identity") — do not
# also run a second script that consumes inbox for the same agent.
set -euo pipefail

AGENT_NAME="${HERMES_AGENT_NAME:?Set HERMES_AGENT_NAME (e.g. via EnvironmentFile=%h/.hermes-bridge/.env in the systemd unit)}"
LOG="${HERMES_BRIDGE_LOG:-$HOME/.hermes-bridge/radio-poll.log}"
mkdir -p "$(dirname "$LOG")"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [$AGENT_NAME] $*" >> "$LOG"; }

result=$(agentbridge inbox --json)
new_count=$(python3 -c 'import json,sys; print(len(json.load(sys.stdin)["messages"]))' <<< "$result")
[ "$new_count" -eq 0 ] && exit 0

log "${new_count} new message(s)"

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
does not). A direct DM to you always gets at least a short reply — see the
skill's "When to Actually Reply" section. If you reply, send it yourself
right now with \`agentbridge dm\` or \`agentbridge send --room\`. If nothing
warrants a reply, just say so briefly — do not invent busywork.
PROMPTEOF
)

agentbridge presence set thinking >/dev/null 2>&1 || true

# Deliberately outside `set -e`: a timed-out or failed hand-off must still
# clear presence back to idle below, not abort the script mid-"thinking".
set +e
reply=$(timeout 180 hermes -z "$prompt" -t terminal --skills agentbridge-client 2>>"$LOG")
handoff_status=$?
set -e

agentbridge presence set idle >/dev/null 2>&1 || true

if [ "$handoff_status" -ne 0 ]; then
  log "agent handoff FAILED (exit $handoff_status): ${reply:0:200}"
else
  log "agent handoff done: ${reply:0:200}"
fi
