#!/usr/bin/env bash
# Hermes Bridge — coordinator install script.
#
# Usage (run as root, on the coordinator VPS):
#   sudo ./deploy/install-server.sh <domain> [repo-url] [agent-names]
#
# Or as a one-liner on a fresh box with nothing cloned yet:
#   curl -fsSL <raw-url-of-this-script> | sudo bash -s -- <domain> <repo-url> [agent-names]
#
# <agent-names> is an optional comma-separated list (e.g. "boss,surrogate1,surrogate2")
# — each is registered immediately and its one-time token printed at the end.
#
# Idempotent: safe to re-run (e.g. after a git pull) to pick up code/service changes.
# Existing /etc/hermes-bridge/server.env and registered agents are never overwritten.
set -euo pipefail

DOMAIN="${1:?Usage: install-server.sh <domain> [repo-url] [agent-names]}"
REPO_URL="${2:-${HERMES_BRIDGE_REPO_URL:-}}"
AGENT_NAMES="${3:-}"
INSTALL_DIR="${HERMES_BRIDGE_INSTALL_DIR:-/opt/hermes-bridge}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this as root (sudo)." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

mkdir -p "$INSTALL_DIR"

if [ -f "$LOCAL_REPO_ROOT/pyproject.toml" ]; then
  echo "==> Using local checkout at $LOCAL_REPO_ROOT"
  if [ "$LOCAL_REPO_ROOT" != "$INSTALL_DIR" ]; then
    echo "==> Copying it into $INSTALL_DIR"
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --exclude .venv --exclude .git --exclude data --exclude __pycache__ \
        "$LOCAL_REPO_ROOT"/ "$INSTALL_DIR"/
    else
      cp -a "$LOCAL_REPO_ROOT"/. "$INSTALL_DIR"/
      rm -rf "${INSTALL_DIR:?}/.venv" "$INSTALL_DIR/.git" "$INSTALL_DIR/data"
    fi
  fi
else
  : "${REPO_URL:?No local repo found next to this script — pass a git URL as the 2nd argument}"
  if [ -d "$INSTALL_DIR/.git" ]; then
    echo "==> Updating existing checkout at $INSTALL_DIR"
    git -C "$INSTALL_DIR" pull --ff-only
  else
    echo "==> Cloning $REPO_URL into $INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR"
  fi
fi

cd "$INSTALL_DIR"

echo "==> Ensuring python3-venv is available"
if ! python3 -m venv --help >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y && apt-get install -y python3-venv
  else
    echo "python3's venv module is unavailable and this isn't a Debian/Ubuntu system — install it manually, then re-run." >&2
    exit 1
  fi
fi

echo "==> Creating virtualenv and installing hermes-bridge[server] (this can take a minute)"
[ -d .venv ] || python3 -m venv .venv
# Older/system pip can fail with "missing the 'build_editable' hook" on an editable
# install of this package — upgrading pip first avoids that.
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -e ".[server]"

echo "==> Creating the hermes-bridge system user"
id hermes-bridge >/dev/null 2>&1 || useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin hermes-bridge

echo "==> Creating data directories"
mkdir -p /var/lib/hermes-bridge/files /etc/hermes-bridge
chown -R hermes-bridge:hermes-bridge "$INSTALL_DIR" /var/lib/hermes-bridge

echo "==> Writing server config"
if [ ! -f /etc/hermes-bridge/server.env ]; then
  cp deploy/server.env.example /etc/hermes-bridge/server.env
  chmod 640 /etc/hermes-bridge/server.env
  chown root:hermes-bridge /etc/hermes-bridge/server.env
else
  echo "    /etc/hermes-bridge/server.env already exists — leaving it untouched"
fi

hbs() { sudo -u hermes-bridge env HERMES_DATA_DIR=/var/lib/hermes-bridge "$INSTALL_DIR/.venv/bin/hermes-bridge-server" "$@"; }

echo "==> Initializing the database"
hbs init-db

if [ -n "$AGENT_NAMES" ]; then
  echo "==> Registering agent identities: $AGENT_NAMES"
  IFS=',' read -ra NAMES <<< "$AGENT_NAMES"
  for name in "${NAMES[@]}"; do
    name="$(echo "$name" | xargs)"
    [ -z "$name" ] && continue
    echo "--- $name ---"
    hbs register-agent "$name" || echo "    (skipped — probably already registered)"
  done
  echo "    COPY THE TOKEN(S) ABOVE NOW — they cannot be shown again."
fi

echo "==> Installing the systemd service"
cp deploy/hermes-bridge.service /etc/systemd/system/hermes-bridge.service
systemctl daemon-reload
systemctl enable --now hermes-bridge
sleep 1
systemctl --no-pager --lines=0 status hermes-bridge || true

echo "==> Setting up Caddy for TLS"
if command -v caddy >/dev/null 2>&1; then
  sed "s/bridge.example.com/$DOMAIN/" deploy/Caddyfile.example > /etc/caddy/Caddyfile
  systemctl reload caddy
  echo "    Caddy configured for $DOMAIN"
else
  echo "    Caddy not found. Install it (https://caddyserver.com/docs/install), then run:"
  echo "      sed 's/bridge.example.com/$DOMAIN/' $INSTALL_DIR/deploy/Caddyfile.example | sudo tee /etc/caddy/Caddyfile"
  echo "      sudo systemctl reload caddy"
fi

cat <<EOF

==> Done.

Verify:
  curl -s https://$DOMAIN/v1/health

Register more agent identities any time:
  sudo -u hermes-bridge env HERMES_DATA_DIR=/var/lib/hermes-bridge \\
    $INSTALL_DIR/.venv/bin/hermes-bridge-server register-agent <name>

Onboard a client machine with each identity's token using deploy/install-client.sh.
EOF
