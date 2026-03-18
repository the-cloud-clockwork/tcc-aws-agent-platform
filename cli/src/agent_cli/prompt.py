"""Prompt sub-commands: push, get, list, diff, rollback, promote.

Communicates with the Prompt Registry API (P04) via httpx.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

prompt_app = typer.Typer(no_args_is_help=True)
console = Console()

_PROMPT_ID_HELP = "Prompt identifier"

# Registry base URL — override with AGENT_REGISTRY_URL env var
REGISTRY_URL = "http://localhost:8000"


def _get_registry_url() -> str:
    import os
    return os.environ.get("AGENT_REGISTRY_URL", REGISTRY_URL)


def _client() -> httpx.Client:
    return httpx.Client(base_url=_get_registry_url(), timeout=30.0)


@prompt_app.command("push")
def push(
    file: Path = typer.Argument(..., help="Path to prompt template file"),
    id: str = typer.Option(..., "--id", help=_PROMPT_ID_HELP),
    version: str = typer.Option(..., "--version", help="Semantic version (e.g. 1.0.0)"),
) -> None:
    """Upload a prompt template to the registry."""
    if not file.exists():
        console.print(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(code=1)

    content = file.read_text(encoding="utf-8")
    payload = {
        "prompt_id": id,
        "version": version,
        "content": content,
        "filename": file.name,
    }

    with _client() as client:
        resp = client.post("/api/v1/prompts", json=payload)

    if resp.status_code in (200, 201):
        console.print(f"[green]Pushed[/green] prompt [bold]{id}[/bold] v{version}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
        raise typer.Exit(code=1)


@prompt_app.command("get")
def get(
    id: str = typer.Argument(..., help=_PROMPT_ID_HELP),
    version: Optional[str] = typer.Option(None, "--version", help="Specific version (default: latest stable)"),
) -> None:
    """Fetch and display a prompt template from the registry."""
    url = f"/api/v1/prompts/{id}"
    params = {}
    if version:
        params["version"] = version

    with _client() as client:
        resp = client.get(url, params=params)

    if resp.status_code == 200:
        data = resp.json()
        console.print(Panel(
            Syntax(data["content"], "jinja2", theme="monokai"),
            title=f"{data['prompt_id']} v{data['version']} [{data.get('status', 'unknown')}]",
            border_style="green",
        ))
    elif resp.status_code == 404:
        console.print(f"[yellow]Not found:[/yellow] prompt {id}" + (f" v{version}" if version else ""))
        raise typer.Exit(code=1)
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
        raise typer.Exit(code=1)


@prompt_app.command("list")
def list_versions(
    id: str = typer.Argument(..., help=_PROMPT_ID_HELP),
) -> None:
    """List all versions of a prompt with their status."""
    with _client() as client:
        resp = client.get(f"/api/v1/prompts/{id}/versions")

    if resp.status_code != 200:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
        raise typer.Exit(code=1)

    versions = resp.json()
    table = Table(title=f"Versions of prompt: {id}")
    table.add_column("Version", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Created", style="dim")
    table.add_column("Hash", style="dim", max_width=12)

    for v in versions:
        status_style = "bold green" if v["status"] == "stable" else "yellow"
        table.add_row(
            v["version"],
            f"[{status_style}]{v['status']}[/{status_style}]",
            v.get("created_at", "\u2014"),
            v.get("content_hash", "\u2014")[:12],
        )

    console.print(table)


@prompt_app.command("diff")
def diff(
    id: str = typer.Argument(..., help=_PROMPT_ID_HELP),
    v1: str = typer.Argument(..., help="First version"),
    v2: str = typer.Argument(..., help="Second version"),
) -> None:
    """Show unified diff between two prompt versions."""
    with _client() as client:
        resp1 = client.get(f"/api/v1/prompts/{id}", params={"version": v1})
        resp2 = client.get(f"/api/v1/prompts/{id}", params={"version": v2})

    if resp1.status_code != 200:
        console.print(f"[red]Error fetching v{v1}:[/red] {resp1.text}")
        raise typer.Exit(code=1)
    if resp2.status_code != 200:
        console.print(f"[red]Error fetching v{v2}:[/red] {resp2.text}")
        raise typer.Exit(code=1)

    lines1 = resp1.json()["content"].splitlines(keepends=True)
    lines2 = resp2.json()["content"].splitlines(keepends=True)

    unified = difflib.unified_diff(
        lines1, lines2,
        fromfile=f"{id} v{v1}",
        tofile=f"{id} v{v2}",
    )
    diff_text = "".join(unified)

    if not diff_text:
        console.print("[dim]No differences found.[/dim]")
    else:
        console.print(Syntax(diff_text, "diff", theme="monokai"))


@prompt_app.command("promote")
def promote(
    id: str = typer.Argument(..., help=_PROMPT_ID_HELP),
    version: str = typer.Argument(..., help="Version to promote to stable"),
) -> None:
    """Promote a prompt version to stable status."""
    with _client() as client:
        resp = client.post(f"/api/v1/prompts/{id}/versions/{version}/promote")

    if resp.status_code == 200:
        console.print(f"[green]Promoted[/green] prompt [bold]{id}[/bold] v{version} to [bold]stable[/bold]")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
        raise typer.Exit(code=1)


@prompt_app.command("rollback")
def rollback(
    id: str = typer.Argument(..., help=_PROMPT_ID_HELP),
    version: str = typer.Argument(..., help="Version to rollback to"),
) -> None:
    """Rollback a prompt to a previous version (marks it as stable, demotes current)."""
    with _client() as client:
        resp = client.post(f"/api/v1/prompts/{id}/versions/{version}/rollback")

    if resp.status_code == 200:
        console.print(f"[green]Rolled back[/green] prompt [bold]{id}[/bold] to v{version}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
        raise typer.Exit(code=1)
