from __future__ import annotations

import typer

from . import db as db_mod
from .config import get_settings

app = typer.Typer(help="Hermes Bridge server administration")


@app.command("init-db")
def init_db_cmd() -> None:
    settings = get_settings()
    db_mod.init_db(settings.resolved_db_path)
    typer.echo(f"Initialized database at {settings.resolved_db_path}")


@app.command("register-agent")
def register_agent_cmd(name: str) -> None:
    settings = get_settings()
    db_mod.init_db(settings.resolved_db_path)
    conn = db_mod.connect(settings.resolved_db_path)
    try:
        if db_mod.get_agent_by_name(conn, name) is not None:
            typer.echo(f"Agent '{name}' already exists.", err=True)
            raise typer.Exit(code=1)
        _row, token = db_mod.create_agent(conn, name)
        typer.echo(f"Registered agent '{name}'. Token (shown once, copy now):")
        typer.echo(token)
    finally:
        conn.close()


@app.command("list-agents")
def list_agents_cmd(
    all_agents: bool = typer.Option(False, "--all", help="Include revoked agents"),
) -> None:
    settings = get_settings()
    db_mod.init_db(settings.resolved_db_path)
    conn = db_mod.connect(settings.resolved_db_path)
    try:
        rows = db_mod.list_agents(conn, active_only=not all_agents)
        for row in rows:
            state = "active" if row["is_active"] else "revoked"
            typer.echo(f"{row['name']}\t{state}\t{row['created_at']}")
    finally:
        conn.close()


@app.command("revoke-agent")
def revoke_agent_cmd(name: str) -> None:
    settings = get_settings()
    conn = db_mod.connect(settings.resolved_db_path)
    try:
        if not db_mod.revoke_agent(conn, name):
            typer.echo(f"No such agent '{name}'", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"Revoked agent '{name}'")
    finally:
        conn.close()


@app.command("serve")
def serve_cmd(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(8000, help="Bind port"),
    reload: bool = typer.Option(False, help="Auto-reload on code changes (dev only)"),
) -> None:
    import uvicorn

    settings = get_settings()
    db_mod.init_db(settings.resolved_db_path)
    uvicorn.run(
        "hermes_bridge.server.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    app()
