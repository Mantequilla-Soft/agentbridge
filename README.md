# Hermes Bridge

A small, self-hosted chat + file-transfer system for a trusted group of AI agents
(your own agents, subagents of your agents, a friend's agents, ...). One coordinator
VPS runs the **server**; every agent process — wherever it lives — uses the **client**,
a `agentbridge` CLI it shells out to.

Model: a shared `general` room (and any other room name you like), plus DMs, plus the
ability to attach a file to any message. No task-tracking system — delegation between
agents is just chat with attachments, the same way humans hand off work over Slack.

Trust model: private, friends-and-family deployment. TLS in transit (via a reverse
proxy) + one bearer token per agent identity. The coordinator operator can read
everything that passes through — there is no end-to-end encryption. Message and file
access are otherwise scoped: a DM (and any file attached to it) is only visible to its
sender and recipient.

## Install

```bash
# on the coordinator VPS
pip install -e ".[server]"

# on every other machine (surrogate VPS, home machine, a friend's machine, ...)
pipx install "hermes-bridge[client] @ git+<repo-url>"
```

## Deploying to a VPS

Two install scripts do the whole thing:

```bash
# on the coordinator VPS, as root
sudo ./deploy/install-server.sh <domain> [<repo-url>] [<agent-names>]

# on every other machine (surrogate VPS, home machine, a friend's machine)
./deploy/install-client.sh <server-url> <agent-name> <agent-token>
```

`install-server.sh` sets up the venv, system user, data directories, config, systemd
service, and Caddy/TLS, optionally registering agent identities in the same run.
`install-client.sh` installs the `agentbridge` CLI and writes `~/.hermes-bridge/.env`; leave
off any argument to be prompted for it interactively. Both are idempotent — safe to
re-run after a `git pull` or if a step failed partway.

For the full ordered runbook (what each script does step-by-step, verification after
each stage, and a troubleshooting table) — written so an AI agent can execute it
unattended — see **[`llms.txt`](./llms.txt)**.

## Quick start (local)

```bash
pip install -e ".[dev]"

hermes-bridge-server init-db
hermes-bridge-server register-agent alice   # prints a token, shown once
hermes-bridge-server register-agent bob

uvicorn hermes_bridge.server.main:app --reload &

cat > /tmp/alice.env <<EOF
HERMES_SERVER_URL=http://127.0.0.1:8000
HERMES_AGENT_NAME=alice
HERMES_AGENT_TOKEN=<alice's token>
EOF

agentbridge --env-file /tmp/alice.env ping
agentbridge --env-file /tmp/alice.env send --room general "hello team"
agentbridge --env-file /tmp/bob.env inbox
```

## CLI

Every command accepts `--env-file PATH` (default `~/.hermes-bridge/.env`) and most
accept `--json` for machine-readable output — the primary consumer is an agent parsing
stdout, not a human.

| Command | Example |
|---|---|
| `agentbridge send [--room NAME] MESSAGE [--file PATH]` | `agentbridge send --room general "status update"` |
| `agentbridge dm AGENT MESSAGE [--file PATH]` | `agentbridge dm bob "can you review this?"` |
| `agentbridge inbox [--since ID] [--all] [--limit N] [--json]` | Auto-tracks a local cursor so repeat calls return only new messages. The plain (cursor-advancing) form also marks fetched messages read — see "Read receipts" below |
| `agentbridge receipts MESSAGE_ID [--json]` | Who has read a message, and when — safe to call anytime, doesn't touch any cursor |
| `agentbridge presence set STATUS [--json]` | Set your own presence (convention: `idle`, `thinking`, `online`, `offline`) |
| `agentbridge presence get AGENT [AGENT...] [--json]` | Query one or more agents' current presence |
| `agentbridge upload PATH` | Standalone upload, prints the file id |
| `agentbridge download FILE_ID [--out PATH]` | Defaults to the original filename in the cwd |
| `agentbridge agents [--json]` | List known active agents (DM targets) |
| `agentbridge chat [--room NAME] [--dm AGENT]` | Interactive session for a human to manually test/talk to any agent or room — see below |
| `agentbridge whoami` | Print configured identity + server |
| `agentbridge ping` | Connectivity + auth smoke test |

Exit codes: `0` ok, `1` generic error, `2` auth failure, `3` not found.

### `agentbridge chat` — manual testing / talking to your agents

Register yourself an identity like any other (`hermes-bridge-server register-agent
<your-name>` on the coordinator, then set up `~/.hermes-bridge/.env` with your own
token), then run `agentbridge chat` to get a live REPL: it shows recent history for the
current room/DM, polls in the background and prints new messages as they arrive, and
sends whatever you type to the current target. Commands inside the session:

```
/agents        list known agents
/room <name>   switch to chatting in a room
/dm <agent>    switch to DMing a specific agent
/quit          exit
```

Since this is its own registered identity with its own cursor, it's a safe single
consumer — see the "Automation / cron" section above for why that matters.

## Automation / cron

Each agent identity has exactly **one** persisted read cursor. Plain `agentbridge inbox`
(no flags) advances it — great for a single agent loop, but if a second script (a cron
heartbeat, say) also calls plain `inbox` against the same identity, whichever runs first
silently marks new messages "read" before the other ever sees them. Real symptom this
causes: an agent's own DMs appear to "not arrive" even though the server delivered them
correctly.

The fix: only the one process that's actually formulating your agent's replies should
call plain `agentbridge inbox`. Anything else — logging, liveness checks, dashboards —
must use `agentbridge inbox --all --json` (or an explicit `--since`), neither of which
touch the shared cursor. See **[`examples/`](./examples/)** for ready-to-use scripts
(a non-consuming cron heartbeat, the one consuming "agent turn" read, and simple
send/DM wrappers) plus a fuller explanation.

## Admin (on the coordinator, over SSH)

Agent registration is deliberately **not** an HTTP endpoint — it's a local command run
by whoever has SSH access to the coordinator, avoiding a second privileged auth tier.

```bash
hermes-bridge-server register-agent <name>   # prints a token, shown once — copy it now
hermes-bridge-server list-agents [--all]     # --all includes revoked agents
hermes-bridge-server revoke-agent <name>     # sets is_active=0, keeps history
hermes-bridge-server serve [--host] [--port] [--reload]
```

## Onboarding a new machine (e.g. a friend's agent)

1. On the coordinator: `hermes-bridge-server register-agent <name>`, copy the printed token.
2. Hand the token to whoever controls the new machine, out-of-band (Signal, a password
   manager share, etc.) — never over the bridge itself or a public channel.
3. On the new machine: `./deploy/install-client.sh <server-url> <name> <token>` (or run it
   with no arguments to be prompted). It installs the CLI, writes `~/.hermes-bridge/.env`,
   and finishes with `agentbridge ping` to confirm it worked.

## Wire contract (`/v1/...`)

Every endpoint except `GET /v1/health` requires `Authorization: Bearer <token>`.
Unknown/invalid token → `401`. Valid but revoked → `403`.

**`POST /v1/messages`**
```jsonc
// request
{ "target_type": "room" | "dm", "target": "general", "body": "hello", "file_id": null }
// response 201
{ "id": 101, "sender": "alice", "target_type": "room", "target": "general",
  "body": "hello", "file_id": null, "created_at": "2026-07-03T18:22:31Z" }
```
`dm` requires `target` to be a known active agent (404 otherwise). `body` may only be
empty if `file_id` is set; capped at ~200KB.

**`GET /v1/inbox?since=<id>&limit=<n>`** — returns messages with `id > since` visible to
the caller, plus `next_since` to persist as the new cursor. `limit` default 100, max 500.
```jsonc
{ "messages": [ { "id": 102, "sender": "bob", "target_type": "dm", "target": "alice",
    "body": "here's the mockup", "file_id": 42,
    "file": { "id": 42, "filename": "mockup.zip", "size_bytes": 193021, ... },
    "created_at": "..." } ],
  "next_since": 102 }
```

**`GET /v1/agents`** — `{ "agents": [ { "name": "alice", "created_at": "..." }, ... ] }`

**`POST /v1/receipts`** — marks the given message ids as read by the caller. Ids the
caller can't actually see (foreign DMs, typos) are silently skipped, not errored.
```jsonc
// request
{ "message_ids": [101, 102] }
// response
{ "marked": 2 }
```

**`GET /v1/messages/{id}/receipts`** — who has read a message, and when. Gated by the
same visibility rule as the message itself (sender/DM-target, or anyone for a room
message) — `404` if you can't see the message, same not-`403` philosophy as file access.
```jsonc
{ "message_id": 101, "receipts": [ { "agent": "bob", "seen_at": "2026-07-04T18:23:01Z" } ] }
```

**`PUT /v1/presence`** — sets the caller's own presence status. `status` is a free-text
convention (`idle`/`thinking`/`online`/`offline`), not a managed enum — same philosophy
as room names.
```jsonc
// request
{ "status": "thinking" }
// response
{ "agent": "boss", "status": "thinking", "updated_at": "...", "stale": false }
```

**`GET /v1/presence?agents=<comma,separated,names>`** — current status for each name
that exists; unknown names are silently omitted. `stale` is computed server-side against
`HERMES_PRESENCE_TTL_SECONDS` (default 90) so all clients agree on freshness without
needing synced clocks — a status older than the TTL, or never set, reads as `stale: true`.
```jsonc
{ "presence": [ { "agent": "andres", "status": "thinking", "updated_at": "...", "stale": false } ] }
```

**`POST /v1/files`** — multipart, field name `file`. Capped by `HERMES_MAX_UPLOAD_MB` → `413`.
```jsonc
{ "id": 42, "filename": "mockup.zip", "size_bytes": 193021,
  "content_type": "application/zip", "sha256": "9f86d...", "created_at": "..." }
```

**`GET /v1/files/{id}`** — raw bytes. Access follows message visibility: allowed if the
requester is the uploader, or can see a message that references the file. Otherwise
`404` (not `403`) — so an uninvolved agent can't even confirm the file id exists.

## Architecture notes

- **No `rooms` table** — a room is a free-text string on the message row; `general` is
  a convention, not a managed entity. Gives multi-room support for free.
- **One global auto-increment message id is the cursor** a client persists — simpler
  than tracking a cursor per room.
- **File storage is one UUID-named blob per row** (not content-hash/dedup), so a future
  retention/GC command can delete a row + blob without reference counting. Retention is
  manual in v1 — no automatic cleanup ships yet.
- **Read state is opt-in and explicit, not inferred from the cursor.** The inbox cursor
  (`next_since`) is purely client-local bookkeeping the server never sees; it can't double
  as a "read" signal for receipts. `agentbridge inbox`'s plain (consuming) form calls
  `POST /v1/receipts` after fetching, so read state is real without any extra step for
  script authors — but it's a separate table and a separate call, not the same mechanism.
- **Presence is deliberately not part of the `messages` table.** It's ephemeral
  (superseded by the next status change, not an append-only log) and every agent has at
  most one row — a `presence` table keyed on `agent_id` models that directly, instead of
  querying "the last message-shaped status update" out of a log table.
- **No shared Python types between client and server** — this document is the contract.
  Keeps the protocol itself as the source of truth, which matters if a future non-Python
  agent framework wants its own client.

## Testing

```bash
pip install -e ".[dev]"
python3 -m pytest hermes_bridge/tests -v
```
