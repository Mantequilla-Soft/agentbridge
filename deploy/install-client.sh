#!/usr/bin/env bash
# Hermes Bridge — client install script.
#
# Usage (run as the user that will operate this agent, no root needed):
#   ./deploy/install-client.sh <server-url> <agent-name> <agent-token> [repo-url]
#
# Or as a one-liner on a fresh machine with nothing cloned yet:
#   curl -fsSL <raw-url-of-this-script> | bash -s -- <server-url> <agent-name> <agent-token> <repo-url>
#
# Any argument left out is prompted for interactively. Installs the `bridge` CLI
# (via pipx if available, else a dedicated venv), writes ~/.hermes-bridge/.env,
# and verifies the connection with `bridge ping`.
set -euo pipefail

SERVER_URL="${1:-}"
AGENT_NAME="${2:-}"
AGENT_TOKEN="${3:-}"
REPO_URL="${4:-${HERMES_BRIDGE_REPO_URL:-}}"

prompt() {
  local var="$1" msg="$2" val
  if [ -n "${!var:-}" ]; then return; fi
  read -r -p "$msg: " val
  printf -v "$var" '%s' "$val"
}

prompt SERVER_URL "Coordinator URL (e.g. https://bridge.example.com)"
prompt AGENT_NAME "This agent's name (as registered on the coordinator)"
prompt AGENT_TOKEN "This agent's token (printed once at registration on the coordinator)"

echo "==> Installing the bridge CLI"
if command -v bridge >/dev/null 2>&1; then
  echo "    'bridge' is already on PATH, skipping install"
else
  prompt REPO_URL "Git URL to install hermes-bridge from"
  if command -v pipx >/dev/null 2>&1; then
    pipx install "hermes-bridge[client] @ git+${REPO_URL}"
  else
    echo "    pipx not found — using a dedicated venv at ~/.hermes-bridge-venv instead"
    python3 -m venv "$HOME/.hermes-bridge-venv"
    "$HOME/.hermes-bridge-venv/bin/pip" install --upgrade pip -q
    "$HOME/.hermes-bridge-venv/bin/pip" install -q "hermes-bridge[client] @ git+${REPO_URL}"
    mkdir -p "$HOME/.local/bin"
    ln -sf "$HOME/.hermes-bridge-venv/bin/bridge" "$HOME/.local/bin/bridge"
    case ":$PATH:" in
      *":$HOME/.local/bin:"*) ;;
      *) echo "    NOTE: add $HOME/.local/bin to your PATH (not currently on it)" ;;
    esac
  fi
fi

BRIDGE_BIN="$(command -v bridge || echo "$HOME/.local/bin/bridge")"

echo "==> Writing ~/.hermes-bridge/.env"
mkdir -p "$HOME/.hermes-bridge"
cat > "$HOME/.hermes-bridge/.env" <<EOF
HERMES_SERVER_URL=${SERVER_URL}
HERMES_AGENT_NAME=${AGENT_NAME}
HERMES_AGENT_TOKEN=${AGENT_TOKEN}
EOF
chmod 600 "$HOME/.hermes-bridge/.env"

echo "==> Verifying connection"
"$BRIDGE_BIN" ping

cat <<EOF

==> Done. This machine is registered as '${AGENT_NAME}' against ${SERVER_URL}.

Try:
  bridge send --room general "hello from ${AGENT_NAME}"
  bridge inbox
EOF
