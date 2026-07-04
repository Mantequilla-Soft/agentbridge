from __future__ import annotations

import json as json_mod
from pathlib import Path
from typing import Optional

import httpx
import typer
from pydantic import ValidationError

from .api import BridgeClient, BridgeError
from .chat import ChatSession, Target
from .config import load_settings
from .state import read_cursor, write_cursor

app = typer.Typer(help="Hermes Bridge client — chat + file transfer for AI agents", no_args_is_help=True)


@app.callback()
def main(
    ctx: typer.Context,
    env_file: Optional[Path] = typer.Option(
        None, "--env-file", help="Path to .env file (default: ~/.hermes-bridge/.env)"
    ),
) -> None:
    ctx.obj = {"env_file": env_file}


def _load_settings(ctx: typer.Context):
    env_file = ctx.obj.get("env_file") if ctx.obj else None
    try:
        return load_settings(env_file)
    except ValidationError as e:
        typer.echo(f"Configuration error: {e}", err=True)
        raise typer.Exit(code=1)


def _get_client(ctx: typer.Context) -> BridgeClient:
    return BridgeClient(_load_settings(ctx))


def _fail(err: Exception) -> "typer.Exit":
    if isinstance(err, BridgeError):
        typer.echo(f"Error: {err}", err=True)
        return typer.Exit(code=err.exit_code)
    if isinstance(err, httpx.RequestError):
        typer.echo(f"Error: could not reach server ({err})", err=True)
        return typer.Exit(code=1)
    raise err


def _print_message(result: dict, json_out: bool) -> None:
    if json_out:
        typer.echo(json_mod.dumps(result, indent=2))
    else:
        typer.echo(f"[{result['id']}] sent to {result['target_type']}:{result['target']}")


@app.command()
def send(
    ctx: typer.Context,
    message: str,
    room: str = typer.Option("general", "--room", help="Room name"),
    file: Optional[Path] = typer.Option(None, "--file", help="Attach a file (uploads then attaches)"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Send a message to a room (defaults to 'general')."""
    client = _get_client(ctx)
    try:
        file_id = client.upload(file)["id"] if file is not None else None
        result = client.send("room", room, message, file_id)
    except Exception as e:
        client.close()
        raise _fail(e)
    client.close()
    _print_message(result, json_out)


@app.command()
def dm(
    ctx: typer.Context,
    agent: str,
    message: str,
    file: Optional[Path] = typer.Option(None, "--file", help="Attach a file (uploads then attaches)"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Send a direct message to another agent."""
    client = _get_client(ctx)
    try:
        file_id = client.upload(file)["id"] if file is not None else None
        result = client.send("dm", agent, message, file_id)
    except Exception as e:
        client.close()
        raise _fail(e)
    client.close()
    _print_message(result, json_out)


@app.command()
def inbox(
    ctx: typer.Context,
    since: Optional[int] = typer.Option(None, "--since", help="Fetch messages after this id"),
    all_messages: bool = typer.Option(False, "--all", help="Fetch full history (same as --since 0)"),
    limit: int = typer.Option(100, "--limit"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Fetch new messages. With no flags, auto-tracks a local cursor so repeated calls return only new messages."""
    settings = _load_settings(ctx)
    client = BridgeClient(settings)
    use_auto_cursor = since is None and not all_messages
    cursor = 0 if all_messages else (since if since is not None else read_cursor(settings.agent_name))
    try:
        result = client.inbox(cursor, limit)
        if use_auto_cursor and result["messages"]:
            try:
                client.mark_read([m["id"] for m in result["messages"]])
            except Exception:
                pass  # best-effort: a read receipt is a courtesy, not the critical path
    except Exception as e:
        client.close()
        raise _fail(e)
    client.close()

    if use_auto_cursor:
        write_cursor(settings.agent_name, result["next_since"])

    if json_out:
        typer.echo(json_mod.dumps(result, indent=2))
        return
    if not result["messages"]:
        typer.echo("(no new messages)")
        return
    for m in result["messages"]:
        where = f"#{m['target']}" if m["target_type"] == "room" else f"@{m['sender']} -> {m['target']}"
        file_note = f" [file: {m['file']['filename']} id={m['file']['id']}]" if m.get("file") else ""
        typer.echo(f"[{m['id']}] {m['sender']} {where}: {m['body']}{file_note}")


@app.command()
def upload(ctx: typer.Context, path: Path, json_out: bool = typer.Option(False, "--json")) -> None:
    """Upload a file standalone, printing its file id."""
    client = _get_client(ctx)
    try:
        result = client.upload(path)
    except Exception as e:
        client.close()
        raise _fail(e)
    client.close()
    if json_out:
        typer.echo(json_mod.dumps(result, indent=2))
    else:
        typer.echo(f"Uploaded '{result['filename']}' as file id {result['id']} ({result['size_bytes']} bytes)")


@app.command()
def download(
    ctx: typer.Context,
    file_id: int,
    out: Optional[Path] = typer.Option(None, "--out", help="Output path (default: original filename in cwd)"),
) -> None:
    """Download a file by id."""
    client = _get_client(ctx)
    try:
        content, suggested_name = client.download(file_id)
    except Exception as e:
        client.close()
        raise _fail(e)
    client.close()
    dest = out or Path(suggested_name)
    dest.write_bytes(content)
    typer.echo(f"Saved to {dest} ({len(content)} bytes)")


@app.command()
def agents(ctx: typer.Context, json_out: bool = typer.Option(False, "--json")) -> None:
    """List known active agents (DM targets)."""
    client = _get_client(ctx)
    try:
        result = client.agents()
    except Exception as e:
        client.close()
        raise _fail(e)
    client.close()
    if json_out:
        typer.echo(json_mod.dumps(result, indent=2))
    else:
        for a in result["agents"]:
            typer.echo(a["name"])


@app.command()
def receipts(ctx: typer.Context, message_id: int, json_out: bool = typer.Option(False, "--json")) -> None:
    """Show who has read a message, and when (non-consuming, safe to call anytime)."""
    client = _get_client(ctx)
    try:
        result = client.message_receipts(message_id)
    except Exception as e:
        client.close()
        raise _fail(e)
    client.close()
    if json_out:
        typer.echo(json_mod.dumps(result, indent=2))
        return
    if not result["receipts"]:
        typer.echo("(not read yet)")
        return
    for r in result["receipts"]:
        typer.echo(f"read by {r['agent']} at {r['seen_at']}")


presence_app = typer.Typer(help="Set or query agent presence status")
app.add_typer(presence_app, name="presence")


@presence_app.command("set")
def presence_set(ctx: typer.Context, status_value: str, json_out: bool = typer.Option(False, "--json")) -> None:
    """Set your own presence status (convention: idle, thinking, online, offline)."""
    client = _get_client(ctx)
    try:
        result = client.set_presence(status_value)
    except Exception as e:
        client.close()
        raise _fail(e)
    client.close()
    if json_out:
        typer.echo(json_mod.dumps(result, indent=2))
    else:
        typer.echo(f"presence set to '{result['status']}'")


@presence_app.command("get")
def presence_get(
    ctx: typer.Context,
    agent_names: list[str] = typer.Argument(..., help="Agent name(s) to check"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Query one or more agents' current presence status."""
    client = _get_client(ctx)
    try:
        result = client.get_presence(agent_names)
    except Exception as e:
        client.close()
        raise _fail(e)
    client.close()
    if json_out:
        typer.echo(json_mod.dumps(result, indent=2))
        return
    for p in result["presence"]:
        if p["status"] is None:
            display = "unknown"
        elif p["stale"]:
            display = f"{p['status']} (stale)"
        else:
            display = p["status"]
        typer.echo(f"{p['agent']}: {display}")


@app.command()
def chat(
    ctx: typer.Context,
    room: Optional[str] = typer.Option(None, "--room", help="Start chatting in this room"),
    dm: Optional[str] = typer.Option(None, "--dm", help="Start DMing this agent"),
) -> None:
    """Interactive session: chat with any registered agent or room in real time."""
    settings = _load_settings(ctx)
    client = BridgeClient(settings)
    initial_target = Target("dm", dm) if dm else Target("room", room or "general")
    try:
        ChatSession(client, settings.agent_name, initial_target=initial_target).run()
    finally:
        client.close()


@app.command()
def whoami(ctx: typer.Context) -> None:
    """Print the configured agent identity and server URL."""
    settings = _load_settings(ctx)
    typer.echo(f"agent:  {settings.agent_name}")
    typer.echo(f"server: {settings.server_url}")


@app.command()
def ping(ctx: typer.Context) -> None:
    """Smoke test: confirms connectivity and that the configured token authenticates."""
    client = _get_client(ctx)
    try:
        client.health()
        client.agents()
    except Exception as e:
        client.close()
        raise _fail(e)
    typer.echo(f"OK — connected to {client.settings.server_url} as '{client.settings.agent_name}'")
    client.close()


if __name__ == "__main__":
    app()
