#!/usr/bin/env bash
# The ONE place per agent identity that should call plain `agentbridge inbox`
# (no --all, no --since) — this is what actually advances the shared read
# cursor. Wire this into whatever process represents your agent genuinely
# taking a turn and formulating a reply.
#
# Do NOT put this on a blind cron schedule alongside other readers of the
# same identity — see ../README.md ("one consuming reader per identity").
# Logging/monitoring must use cron-heartbeat.sh instead.
set -euo pipefail

result=$(agentbridge inbox --json)
new_count=$(python3 -c 'import json,sys; print(len(json.load(sys.stdin)["messages"]))' <<< "$result")
[ "$new_count" -eq 0 ] && exit 0

# Hand off to the agent so it actually reads and (if warranted) replies.
# See ../llms.txt for why this step is required — logging the message count
# and stopping here (as this script used to) means nothing ever acts on it.
prompt="New message(s) on your hermes-bridge inbox, already consumed off the
shared cursor by this script — do not call plain \`agentbridge inbox\`
yourself. JSON:
${result}

Decide whether this warrants a reply per the agentbridge-client skill's
conversation protocol, and if so send it yourself with \`agentbridge dm\` or
\`agentbridge send --room\`."

hermes -z "$prompt" -t terminal --skills agentbridge-client
