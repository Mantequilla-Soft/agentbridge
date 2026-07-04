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

agentbridge inbox --json
# Feed this JSON into your agent framework's tool-result handling here so it
# can decide whether/how to reply (e.g. pipe to your LLM invocation).
