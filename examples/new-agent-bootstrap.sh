#!/usr/bin/env bash
# New-agent bootstrap for agentbridge.
# Run this on a fresh machine, then send the final 3-line verification output to boss.
set -euo pipefail

AGENT_NAME="${HERMES_AGENT_NAME:?Set HERMES_AGENT_NAME first}"
BRIDGE_BIN="$HOME/.hermes-bridge/bin"
BRIDGE_STATE="$HOME/.hermes-bridge/state"
SYSTEMD_USER="$HOME/.config/systemd/user"
AGENTBRIDGE_REPO="${AGENTBRIDGE_REPO:-$HOME/agentbridge}"

echo "[bootstrap] bootstrapping agent=$AGENT_NAME repo=$AGENTBRIDGE_REPO"

SKILLS_DIR="$HOME/.hermes/skills/messaging/agentbridge-client"

mkdir -p "$BRIDGE_BIN" "$BRIDGE_STATE" "$SYSTEMD_USER"

# 0) Skill — the hand-off in radio-poll.sh loads this via --skills, so the
# agent needs it on disk before polling can actually produce a reply. Never
# overwrite an existing copy: a machine may have a customized version with
# its own operational sections layered on top of the generic base.
if [ -d "$SKILLS_DIR" ]; then
  echo "[bootstrap] skill already present at $SKILLS_DIR — leaving it alone"
else
  mkdir -p "$(dirname "$SKILLS_DIR")"
  cp -r "$AGENTBRIDGE_REPO/examples/skills/agentbridge-client" "$SKILLS_DIR"
  echo "[bootstrap] installed generic agentbridge-client skill to $SKILLS_DIR"
fi

if ! command -v hermes >/dev/null 2>&1; then
  echo "[bootstrap] 'hermes' not found on PATH — radio-poll.sh's agent hand-off will fail without it" >&2
  exit 1
fi

# 1) Wrappers
cp "$AGENTBRIDGE_REPO/examples/"send-dm.sh "$AGENTBRIDGE_REPO/examples/"send-room-message.sh \
   "$AGENTBRIDGE_REPO/examples/"enter-active-mode.sh "$AGENTBRIDGE_REPO/examples/"radio-poll.sh \
   "$AGENTBRIDGE_REPO/examples/"cron-heartbeat.sh "$AGENTBRIDGE_REPO/examples/"agent-turn.sh \
   "$BRIDGE_BIN/"
chmod +x "$BRIDGE_BIN"/*.sh

# 2) systemd units
cp "$AGENTBRIDGE_REPO/examples/"radio-poll.service "$AGENTBRIDGE_REPO/examples/"radio-poll.timer "$SYSTEMD_USER/"
sed -i "s|ExecStart=.*|ExecStart=$AGENTBRIDGE_REPO/examples/radio-poll.sh|" "$SYSTEMD_USER/radio-poll.service"

# 3) state file
date +%s > "$BRIDGE_STATE/${AGENT_NAME}-active-since"

# 4) ping
if [ -f "$HOME/.hermes-bridge/.env" ]; then
  # shellcheck disable=SC1090
  source "$HOME/.hermes-bridge/.env"
else
  echo "[bootstrap] missing ~/.hermes-bridge/.env — create it from coordinator template before continuing" >&2
  exit 1
fi

if ! command -v agentbridge >/dev/null 2>&1 && [ ! -x "$HOME/.hermes-bridge-venv/bin/agentbridge" ]; then
  echo "[bootstrap] agentbridge binary not found — install it first (pip/venv or system package)" >&2
  exit 1
fi

AGENTBRIDGE_BIN="${AGENTBRIDGE_BIN:-$HOME/.hermes-bridge-venv/bin/agentbridge}"
"$AGENTBRIDGE_BIN" ping

# 5) systemd
systemctl --user daemon-reload
systemctl --user enable --now radio-poll.timer
loginctl enable-linger "$USER" >/dev/null 2>&1 || true

# 6) hand-off smoke test — proves the LLM invocation radio-poll.sh depends on
# actually works on this machine, not just that the timer is ticking.
HANDOFF_OK="no"
if timeout 60 hermes -z "Reply with exactly the word: pong" -t terminal --skills agentbridge-client 2>/dev/null | grep -qi pong; then
  HANDOFF_OK="yes"
fi

# 7) summary
echo "--- VERIFICATION SUMMARY ---"
echo "AGENT_NAME=$AGENT_NAME"
echo "STATE_FILE=$BRIDGE_STATE/${AGENT_NAME}-active-since"
echo "DID_PING=$( "$AGENTBRIDGE_BIN" ping 2>&1 | head -1 )"
echo "TIMER_STATUS=$(systemctl --user is-active radio-poll.timer 2>/dev/null || echo inactive)"
echo "IDENTITIES=$( "$AGENTBRIDGE_BIN" agents 2>&1 )"
echo "HANDOFF_SMOKE_TEST=$HANDOFF_OK"
if [ "$HANDOFF_OK" != "yes" ]; then
  echo "[bootstrap] WARNING: hermes -z smoke test failed — radio-poll.sh will detect messages but won't be able to act on them. Run the same command manually to see the actual error." >&2
fi
