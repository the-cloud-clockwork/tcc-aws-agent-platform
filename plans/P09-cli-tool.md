# P09 — CLI Tool

## Objective
Build `qitp` CLI tool using Typer. Commands: prompt management (push/get/list/diff/rollback/promote), strategy validation/promotion, blueprint linting, and graph rendering (auto-generate ASCII flow diagrams from multi_agent YAML).

## Plane Tickets
ROOT-48 (CLI part of Prompt Registry scope)

## Target Repo
`~/dev/tccw-agent-cli`

## Dependencies
P02 (core schemas), P04 (prompt registry API)

## Repo Structure
```
tccw-agent-cli/
├── src/
│   └── agent_cli/
│       ├── __init__.py
│       ├── main.py         # Typer app entrypoint
│       ├── prompt.py       # prompt push/get/list/diff/rollback/promote
│       ├── strategy.py     # strategy validate/list/promote
│       ├── blueprint.py    # blueprint lint/validate
│       └── graph.py        # graph render — ASCII flow diagram from YAML multi_agent section
├── tests/
│   ├── test_prompt.py
│   ├── test_strategy.py
│   ├── test_blueprint.py
│   └── test_graph.py
└── pyproject.toml           # with [project.scripts] qitp = "agent_cli.main:app"
```

## Key Commands

| Command | Description |
|---------|-------------|
| `qitp prompt push <file> --id <id> --version <ver>` | Upload prompt to registry |
| `qitp prompt get <id> [--version <ver>]` | Fetch prompt text |
| `qitp prompt list <id>` | All versions with status |
| `qitp prompt diff <id> <v1> <v2>` | Unified diff between versions |
| `qitp prompt promote <id> <ver>` | Set version to stable |
| `qitp prompt rollback <id> <ver>` | Revert to previous version |
| `qitp strategy validate <yaml_path>` | Validate against Pydantic schema |
| `qitp strategy list` | All strategies from blueprints/strategies/ |
| `qitp blueprint lint <yaml_path>` | Validate any blueprint YAML |
| `qitp graph render <agent_yaml_path>` | Generate ASCII topology from multi_agent section |

### Graph Render Output
When given an agent YAML with `multi_agent.pattern=graph`, `multi_agent.nodes`, `multi_agent.edges`, output a markdown file with:
- ASCII box diagram showing nodes and arrows
- Table of nodes (id, agent_ref, type)
- Table of edges (from->to, condition, label)
- Circuit breaker section if any gate nodes

## Libraries
- **Typer** — CLI framework
- **Rich** — terminal formatting, tables, panels
- **httpx** — async HTTP client for Prompt Registry API
- **agent-core** — Pydantic models for validation
- **PyYAML** — YAML parsing

---

## Implementation

### pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent-cli"
version = "0.1.0"
description = "QITP CLI tool for prompt management, strategy validation, and graph rendering"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12.0",
    "rich>=13.7.0",
    "httpx>=0.27.0",
    "pyyaml>=6.0.1",
    "agent-core>=0.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "respx>=0.21.0",
    "pytest-cov>=5.0.0",
]

[project.scripts]
qitp = "agent_cli.main:app"

[tool.hatch.build.targets.wheel]
packages = ["src/agent_cli"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

### src/agent_cli/__init__.py

```python
"""QITP CLI — command-line tool for prompt, strategy, blueprint, and graph management."""

__version__ = "0.1.0"
```

### src/agent_cli/main.py

```python
"""Typer application entrypoint. Registers all sub-command groups."""

import typer

from agent_cli.prompt import prompt_app
from agent_cli.strategy import strategy_app
from agent_cli.blueprint import blueprint_app
from agent_cli.graph import graph_app

app = typer.Typer(
    name="qitp",
    help="QITP CLI — manage prompts, strategies, blueprints, and agent graphs.",
    no_args_is_help=True,
)

app.add_typer(prompt_app, name="prompt", help="Prompt registry operations")
app.add_typer(strategy_app, name="strategy", help="Strategy validation and listing")
app.add_typer(blueprint_app, name="blueprint", help="Blueprint linting and validation")
app.add_typer(graph_app, name="graph", help="Agent graph rendering")


@app.callback()
def main_callback() -> None:
    """QITP CLI — Quantitative Investment Trading Platform."""


if __name__ == "__main__":
    app()
```

### src/agent_cli/prompt.py

```python
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

# Registry base URL — override with QITP_REGISTRY_URL env var
REGISTRY_URL = "http://localhost:8000"


def _get_registry_url() -> str:
    import os
    return os.environ.get("QITP_REGISTRY_URL", REGISTRY_URL)


def _client() -> httpx.Client:
    return httpx.Client(base_url=_get_registry_url(), timeout=30.0)


@prompt_app.command("push")
def push(
    file: Path = typer.Argument(..., help="Path to prompt template file"),
    id: str = typer.Option(..., "--id", help="Prompt identifier"),
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
    id: str = typer.Argument(..., help="Prompt identifier"),
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
    id: str = typer.Argument(..., help="Prompt identifier"),
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
            v.get("created_at", "—"),
            v.get("content_hash", "—")[:12],
        )

    console.print(table)


@prompt_app.command("diff")
def diff(
    id: str = typer.Argument(..., help="Prompt identifier"),
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
    id: str = typer.Argument(..., help="Prompt identifier"),
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
    id: str = typer.Argument(..., help="Prompt identifier"),
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
```

### src/agent_cli/strategy.py

```python
"""Strategy sub-commands: validate, list, promote.

Validates strategy YAML files against agent-core StrategyBlueprint Pydantic model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

strategy_app = typer.Typer(no_args_is_help=True)
console = Console()

# Default strategies directory — override with QITP_STRATEGIES_DIR env var
DEFAULT_STRATEGIES_DIR = "blueprints/strategies"


def _get_strategies_dir() -> Path:
    import os
    return Path(os.environ.get("QITP_STRATEGIES_DIR", DEFAULT_STRATEGIES_DIR))


def _load_yaml(path: Path) -> dict:
    """Load and parse a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _validate_strategy(data: dict) -> tuple[bool, list[str]]:
    """Validate strategy data against StrategyBlueprint Pydantic model.

    Returns (is_valid, list_of_errors).
    """
    try:
        from agent_core.models.strategy import StrategyBlueprint
        StrategyBlueprint.model_validate(data)
        return True, []
    except ImportError:
        # Fallback: basic structural validation if agent-core not installed
        errors = []
        required_fields = [
            "strategy_id", "name", "version", "description",
            "entry_conditions", "exit_conditions", "position_sizing",
        ]
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        return len(errors) == 0, errors
    except Exception as e:
        return False, [str(e)]


@strategy_app.command("validate")
def validate(
    yaml_path: Path = typer.Argument(..., help="Path to strategy YAML file"),
) -> None:
    """Validate a strategy YAML against the StrategyBlueprint schema."""
    if not yaml_path.exists():
        console.print(f"[red]Error:[/red] File not found: {yaml_path}")
        raise typer.Exit(code=1)

    try:
        data = _load_yaml(yaml_path)
    except yaml.YAMLError as e:
        console.print(f"[red]YAML parse error:[/red] {e}")
        raise typer.Exit(code=1)

    is_valid, errors = _validate_strategy(data)

    if is_valid:
        console.print(Panel(
            f"[green]VALID[/green] — {data.get('name', yaml_path.stem)} v{data.get('version', '?')}",
            title=str(yaml_path),
            border_style="green",
        ))
    else:
        console.print(Panel(
            "\n".join(f"[red]x[/red] {e}" for e in errors),
            title=f"Validation errors: {yaml_path}",
            border_style="red",
        ))
        raise typer.Exit(code=1)


@strategy_app.command("list")
def list_strategies(
    directory: Optional[Path] = typer.Option(None, "--dir", help="Strategies directory (default: blueprints/strategies/)"),
) -> None:
    """List all strategy YAML files in the strategies directory."""
    strategies_dir = directory or _get_strategies_dir()

    if not strategies_dir.exists():
        console.print(f"[red]Error:[/red] Directory not found: {strategies_dir}")
        raise typer.Exit(code=1)

    yaml_files = sorted(strategies_dir.glob("*.yaml")) + sorted(strategies_dir.glob("*.yml"))

    if not yaml_files:
        console.print(f"[yellow]No strategy files found in {strategies_dir}[/yellow]")
        return

    table = Table(title=f"Strategies in {strategies_dir}")
    table.add_column("File", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Version", style="green")
    table.add_column("Valid", justify="center")
    table.add_column("Description", max_width=50)

    for f in yaml_files:
        try:
            data = _load_yaml(f)
            is_valid, _ = _validate_strategy(data)
            table.add_row(
                f.name,
                data.get("name", "—"),
                data.get("version", "—"),
                "[green]Y[/green]" if is_valid else "[red]N[/red]",
                (data.get("description", "—") or "—")[:50],
            )
        except Exception as e:
            table.add_row(f.name, "—", "—", "[red]ERR[/red]", str(e)[:50])

    console.print(table)


@strategy_app.command("promote")
def promote(
    yaml_path: Path = typer.Argument(..., help="Path to strategy YAML file"),
) -> None:
    """Promote a strategy to 'stable' status (updates status field in YAML)."""
    if not yaml_path.exists():
        console.print(f"[red]Error:[/red] File not found: {yaml_path}")
        raise typer.Exit(code=1)

    data = _load_yaml(yaml_path)
    is_valid, errors = _validate_strategy(data)

    if not is_valid:
        console.print("[red]Cannot promote invalid strategy:[/red]")
        for e in errors:
            console.print(f"  [red]x[/red] {e}")
        raise typer.Exit(code=1)

    data["status"] = "stable"

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    console.print(f"[green]Promoted[/green] strategy [bold]{data.get('name', yaml_path.stem)}[/bold] to [bold]stable[/bold]")
```

### src/agent_cli/blueprint.py

```python
"""Blueprint sub-commands: lint, validate.

Validates any blueprint YAML (agent or strategy) against agent-core models.
"""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree

blueprint_app = typer.Typer(no_args_is_help=True)
console = Console()


def _detect_blueprint_type(data: dict) -> str:
    """Detect whether a YAML is an agent blueprint or strategy blueprint."""
    if "multi_agent" in data or "agent_id" in data or "model" in data:
        return "agent"
    if "entry_conditions" in data or "exit_conditions" in data or "strategy_id" in data:
        return "strategy"
    return "unknown"


def _validate_agent_blueprint(data: dict) -> tuple[bool, list[str]]:
    """Validate against AgentBlueprint Pydantic model."""
    try:
        from agent_core.models.agent import AgentBlueprint
        AgentBlueprint.model_validate(data)
        return True, []
    except ImportError:
        errors = []
        required = ["agent_id", "name", "version", "model"]
        for field in required:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        return len(errors) == 0, errors
    except Exception as e:
        return False, [str(e)]


def _validate_strategy_blueprint(data: dict) -> tuple[bool, list[str]]:
    """Validate against StrategyBlueprint Pydantic model."""
    try:
        from agent_core.models.strategy import StrategyBlueprint
        StrategyBlueprint.model_validate(data)
        return True, []
    except ImportError:
        errors = []
        required = ["strategy_id", "name", "version", "entry_conditions", "exit_conditions"]
        for field in required:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        return len(errors) == 0, errors
    except Exception as e:
        return False, [str(e)]


@blueprint_app.command("lint")
def lint(
    yaml_path: Path = typer.Argument(..., help="Path to blueprint YAML file"),
) -> None:
    """Lint and validate a blueprint YAML file.

    Auto-detects whether it's an agent or strategy blueprint and validates
    against the appropriate Pydantic schema.
    """
    if not yaml_path.exists():
        console.print(f"[red]Error:[/red] File not found: {yaml_path}")
        raise typer.Exit(code=1)

    try:
        data = _load_yaml(yaml_path)
    except yaml.YAMLError as e:
        console.print(f"[red]YAML parse error:[/red] {e}")
        raise typer.Exit(code=1)

    if data is None:
        console.print(f"[red]Error:[/red] Empty YAML file: {yaml_path}")
        raise typer.Exit(code=1)

    bp_type = _detect_blueprint_type(data)

    if bp_type == "agent":
        is_valid, errors = _validate_agent_blueprint(data)
    elif bp_type == "strategy":
        is_valid, errors = _validate_strategy_blueprint(data)
    else:
        console.print(f"[yellow]Warning:[/yellow] Could not detect blueprint type. Running basic checks.")
        is_valid = True
        errors = []

    # Build a summary tree
    tree = Tree(f"[bold]{yaml_path.name}[/bold] ({bp_type} blueprint)")
    tree.add(f"Name: {data.get('name', '—')}")
    tree.add(f"Version: {data.get('version', '—')}")

    if "model" in data:
        model_branch = tree.add("Model")
        model = data["model"]
        if isinstance(model, dict):
            model_branch.add(f"provider: {model.get('provider', '—')}")
            model_branch.add(f"model_id: {model.get('model_id', '—')}")

    if "multi_agent" in data:
        ma = data["multi_agent"]
        ma_branch = tree.add(f"Multi-Agent: {ma.get('pattern', '—')}")
        if "nodes" in ma:
            ma_branch.add(f"Nodes: {len(ma['nodes'])}")
        if "edges" in ma:
            ma_branch.add(f"Edges: {len(ma['edges'])}")

    if "tools" in data:
        tree.add(f"Tools: {len(data['tools'])}")

    console.print(tree)
    console.print()

    if is_valid:
        console.print(f"[green]PASS[/green] — Blueprint is valid.")
    else:
        console.print(f"[red]FAIL[/red] — {len(errors)} error(s):")
        for e in errors:
            console.print(f"  [red]x[/red] {e}")
        raise typer.Exit(code=1)


@blueprint_app.command("validate")
def validate(
    yaml_path: Path = typer.Argument(..., help="Path to blueprint YAML file"),
) -> None:
    """Alias for lint — validate a blueprint YAML file."""
    lint(yaml_path)


def _load_yaml(path: Path) -> dict:
    """Load and parse a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
```

### src/agent_cli/graph.py

```python
"""Graph sub-commands: render.

Generates ASCII flow diagrams from multi_agent YAML (graph pattern).
Produces a markdown file with:
- ASCII box diagram showing nodes and arrows
- Table of nodes (id, agent_ref, type)
- Table of edges (from->to, condition, label)
- Circuit breaker section if any gate nodes
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

graph_app = typer.Typer(no_args_is_help=True)
console = Console()


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_ascii_diagram(nodes: list[dict], edges: list[dict]) -> str:
    """Build an ASCII box-and-arrow diagram from nodes and edges.

    Produces a top-down flow layout. Each node is rendered as a box:
        +------------------+
        |   node_id        |
        |   (agent_ref)    |
        +------------------+

    Edges are shown as vertical arrows with optional labels.
    """
    if not nodes:
        return "(no nodes defined)"

    # Build adjacency: source -> list of (target, label)
    adjacency: dict[str, list[tuple[str, str]]] = {}
    for edge in edges:
        src = edge.get("from") or edge.get("source", "?")
        tgt = edge.get("to") or edge.get("target", "?")
        label = edge.get("label", "")
        adjacency.setdefault(src, []).append((tgt, label))

    # Topological sort (simple BFS from nodes with no incoming edges)
    node_ids = [n.get("id", n.get("node_id", "?")) for n in nodes]
    incoming = {nid: 0 for nid in node_ids}
    for edge in edges:
        tgt = edge.get("to") or edge.get("target", "?")
        if tgt in incoming:
            incoming[tgt] += 1

    # BFS order
    from collections import deque
    queue = deque([nid for nid, cnt in incoming.items() if cnt == 0])
    ordered = []
    visited = set()
    while queue:
        nid = queue.popleft()
        if nid in visited:
            continue
        visited.add(nid)
        ordered.append(nid)
        for tgt, _ in adjacency.get(nid, []):
            if tgt in incoming:
                incoming[tgt] -= 1
                if incoming[tgt] <= 0 and tgt not in visited:
                    queue.append(tgt)

    # Add any remaining nodes not reached
    for nid in node_ids:
        if nid not in visited:
            ordered.append(nid)

    # Node info lookup
    node_map = {}
    for n in nodes:
        nid = n.get("id", n.get("node_id", "?"))
        node_map[nid] = n

    # Render boxes
    lines = []
    BOX_WIDTH = 30
    INNER = BOX_WIDTH - 4  # inside padding

    for i, nid in enumerate(ordered):
        node = node_map.get(nid, {})
        agent_ref = node.get("agent_ref", node.get("type", ""))
        node_type = node.get("type", "agent")

        # Box top
        lines.append("+" + "-" * (BOX_WIDTH - 2) + "+")
        # Node ID line
        id_line = f"  {nid}"
        lines.append("|" + id_line.ljust(BOX_WIDTH - 2) + "|")
        # Agent ref line
        if agent_ref:
            ref_line = f"  ({agent_ref})"
            lines.append("|" + ref_line.ljust(BOX_WIDTH - 2) + "|")
        # Type line if gate
        if node_type == "gate":
            gate_line = f"  [GATE]"
            lines.append("|" + gate_line.ljust(BOX_WIDTH - 2) + "|")
        # Box bottom
        lines.append("+" + "-" * (BOX_WIDTH - 2) + "+")

        # Draw arrows to next nodes
        targets = adjacency.get(nid, [])
        if targets:
            for tgt, label in targets:
                arrow_label = f" --[{label}]--> {tgt}" if label else f" --> {tgt}"
                lines.append(f"    |{arrow_label}")
            lines.append("    v")

    return "\n".join(lines)


def _build_node_table(nodes: list[dict]) -> str:
    """Build a markdown table of nodes."""
    rows = ["| ID | Agent Ref | Type |", "|---|---|---|"]
    for n in nodes:
        nid = n.get("id", n.get("node_id", "?"))
        agent_ref = n.get("agent_ref", "—")
        node_type = n.get("type", "agent")
        rows.append(f"| {nid} | {agent_ref} | {node_type} |")
    return "\n".join(rows)


def _build_edge_table(edges: list[dict]) -> str:
    """Build a markdown table of edges."""
    rows = ["| From | To | Condition | Label |", "|---|---|---|---|"]
    for e in edges:
        src = e.get("from") or e.get("source", "?")
        tgt = e.get("to") or e.get("target", "?")
        condition = e.get("condition", "—")
        label = e.get("label", "—")
        rows.append(f"| {src} | {tgt} | {condition} | {label} |")
    return "\n".join(rows)


def _build_circuit_breaker_section(nodes: list[dict]) -> str | None:
    """If any gate nodes exist, build a circuit breaker summary."""
    gates = [n for n in nodes if n.get("type") == "gate"]
    if not gates:
        return None

    lines = ["## Circuit Breakers", ""]
    for g in gates:
        gid = g.get("id", g.get("node_id", "?"))
        trip = g.get("trip_condition", "—")
        fallback = g.get("fallback", "—")
        lines.append(f"- **{gid}**: trip=`{trip}`, fallback=`{fallback}`")

    return "\n".join(lines)


@graph_app.command("render")
def render(
    agent_yaml_path: Path = typer.Argument(..., help="Path to agent YAML with multi_agent.pattern=graph"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output markdown file path"),
) -> None:
    """Generate ASCII topology diagram from a multi_agent graph YAML.

    Reads the multi_agent section of an agent blueprint YAML and produces
    a markdown document with:
    - ASCII box diagram
    - Node table
    - Edge table
    - Circuit breaker section (if gate nodes exist)
    """
    if not agent_yaml_path.exists():
        console.print(f"[red]Error:[/red] File not found: {agent_yaml_path}")
        raise typer.Exit(code=1)

    try:
        data = _load_yaml(agent_yaml_path)
    except yaml.YAMLError as e:
        console.print(f"[red]YAML parse error:[/red] {e}")
        raise typer.Exit(code=1)

    multi_agent = data.get("multi_agent")
    if not multi_agent:
        console.print(f"[red]Error:[/red] No multi_agent section found in {agent_yaml_path}")
        raise typer.Exit(code=1)

    pattern = multi_agent.get("pattern", "unknown")
    if pattern != "graph":
        console.print(f"[yellow]Warning:[/yellow] multi_agent.pattern is '{pattern}', not 'graph'. Rendering anyway.")

    nodes = multi_agent.get("nodes", [])
    edges = multi_agent.get("edges", [])

    if not nodes:
        console.print(f"[yellow]Warning:[/yellow] No nodes defined in multi_agent section.")

    # Build markdown
    agent_name = data.get("name", agent_yaml_path.stem)
    sections = [
        f"# Agent Graph: {agent_name}",
        "",
        f"**Pattern:** {pattern}  ",
        f"**Nodes:** {len(nodes)} | **Edges:** {len(edges)}",
        "",
        "## Topology",
        "",
        "```",
        _build_ascii_diagram(nodes, edges),
        "```",
        "",
        "## Nodes",
        "",
        _build_node_table(nodes),
        "",
        "## Edges",
        "",
        _build_edge_table(edges),
    ]

    # Circuit breaker section
    cb_section = _build_circuit_breaker_section(nodes)
    if cb_section:
        sections.extend(["", cb_section])

    markdown = "\n".join(sections) + "\n"

    # Output
    if output:
        output.write_text(markdown, encoding="utf-8")
        console.print(f"[green]Written[/green] graph diagram to {output}")
    else:
        console.print(Panel(markdown, title=f"Graph: {agent_name}", border_style="blue"))

    # Also print Rich summary to terminal
    table = Table(title="Graph Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Pattern", pattern)
    table.add_row("Nodes", str(len(nodes)))
    table.add_row("Edges", str(len(edges)))
    table.add_row("Gate nodes", str(len([n for n in nodes if n.get("type") == "gate"])))
    console.print(table)
```

### tests/test_prompt.py

```python
"""Tests for qitp prompt sub-commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from agent_cli.main import app

runner = CliRunner()


def _mock_response(status_code: int, json_data: dict | None = None, text: str = "") -> httpx.Response:
    """Create a mock httpx.Response."""
    resp = httpx.Response(
        status_code=status_code,
        json=json_data,
        text=text,
        request=httpx.Request("GET", "http://test"),
    )
    return resp


class TestPromptPush:
    def test_push_success(self, tmp_path: Path):
        prompt_file = tmp_path / "test.txt"
        prompt_file.write_text("You are a helpful assistant.")

        with patch("agent_cli.prompt._client") as mock_client:
            mock_ctx = mock_client.return_value.__enter__.return_value
            mock_ctx.post.return_value = _mock_response(201, {"status": "created"})

            result = runner.invoke(app, [
                "prompt", "push", str(prompt_file),
                "--id", "test-prompt",
                "--version", "1.0.0",
            ])

        assert result.exit_code == 0
        assert "Pushed" in result.output

    def test_push_file_not_found(self):
        result = runner.invoke(app, [
            "prompt", "push", "/nonexistent/file.txt",
            "--id", "test", "--version", "1.0.0",
        ])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestPromptGet:
    def test_get_success(self):
        with patch("agent_cli.prompt._client") as mock_client:
            mock_ctx = mock_client.return_value.__enter__.return_value
            mock_ctx.get.return_value = _mock_response(200, {
                "prompt_id": "test-prompt",
                "version": "1.0.0",
                "status": "stable",
                "content": "You are a helpful assistant.",
            })

            result = runner.invoke(app, ["prompt", "get", "test-prompt"])

        assert result.exit_code == 0

    def test_get_not_found(self):
        with patch("agent_cli.prompt._client") as mock_client:
            mock_ctx = mock_client.return_value.__enter__.return_value
            mock_ctx.get.return_value = _mock_response(404)

            result = runner.invoke(app, ["prompt", "get", "missing-prompt"])

        assert result.exit_code == 1


class TestPromptList:
    def test_list_versions(self):
        with patch("agent_cli.prompt._client") as mock_client:
            mock_ctx = mock_client.return_value.__enter__.return_value
            mock_ctx.get.return_value = _mock_response(200, [
                {"version": "1.0.0", "status": "stable", "created_at": "2026-01-01", "content_hash": "abc123"},
                {"version": "0.9.0", "status": "draft", "created_at": "2025-12-01", "content_hash": "def456"},
            ])

            result = runner.invoke(app, ["prompt", "list", "test-prompt"])

        assert result.exit_code == 0


class TestPromptDiff:
    def test_diff_shows_changes(self):
        with patch("agent_cli.prompt._client") as mock_client:
            mock_ctx = mock_client.return_value.__enter__.return_value
            mock_ctx.get.side_effect = [
                _mock_response(200, {"content": "Line 1\nLine 2\n"}),
                _mock_response(200, {"content": "Line 1\nLine 2 modified\n"}),
            ]

            result = runner.invoke(app, ["prompt", "diff", "test-prompt", "1.0.0", "2.0.0"])

        assert result.exit_code == 0


class TestPromptPromote:
    def test_promote_success(self):
        with patch("agent_cli.prompt._client") as mock_client:
            mock_ctx = mock_client.return_value.__enter__.return_value
            mock_ctx.post.return_value = _mock_response(200)

            result = runner.invoke(app, ["prompt", "promote", "test-prompt", "1.0.0"])

        assert result.exit_code == 0
        assert "Promoted" in result.output


class TestPromptRollback:
    def test_rollback_success(self):
        with patch("agent_cli.prompt._client") as mock_client:
            mock_ctx = mock_client.return_value.__enter__.return_value
            mock_ctx.post.return_value = _mock_response(200)

            result = runner.invoke(app, ["prompt", "rollback", "test-prompt", "0.9.0"])

        assert result.exit_code == 0
        assert "Rolled back" in result.output
```

### tests/test_strategy.py

```python
"""Tests for qitp strategy sub-commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_cli.main import app

runner = CliRunner()


VALID_STRATEGY_YAML = """
strategy_id: test-strategy
name: Test Strategy
version: "1.0.0"
description: A test strategy
status: draft
entry_conditions:
  - type: gap_up
    threshold_pct: 2.0
exit_conditions:
  - type: stop_loss
    pct: -1.5
position_sizing:
  method: fixed_fraction
  fraction: 0.02
"""

INVALID_STRATEGY_YAML = """
name: Missing Required Fields
description: No strategy_id or conditions
"""


class TestStrategyValidate:
    def test_validate_valid_strategy(self, tmp_path: Path):
        yaml_file = tmp_path / "strategy.yaml"
        yaml_file.write_text(VALID_STRATEGY_YAML)

        result = runner.invoke(app, ["strategy", "validate", str(yaml_file)])
        assert result.exit_code == 0
        assert "VALID" in result.output

    def test_validate_invalid_strategy(self, tmp_path: Path):
        yaml_file = tmp_path / "bad_strategy.yaml"
        yaml_file.write_text(INVALID_STRATEGY_YAML)

        result = runner.invoke(app, ["strategy", "validate", str(yaml_file)])
        assert result.exit_code == 1

    def test_validate_file_not_found(self):
        result = runner.invoke(app, ["strategy", "validate", "/nonexistent.yaml"])
        assert result.exit_code == 1


class TestStrategyList:
    def test_list_strategies(self, tmp_path: Path):
        (tmp_path / "s1.yaml").write_text(VALID_STRATEGY_YAML)
        (tmp_path / "s2.yaml").write_text(VALID_STRATEGY_YAML)

        result = runner.invoke(app, ["strategy", "list", "--dir", str(tmp_path)])
        assert result.exit_code == 0

    def test_list_empty_directory(self, tmp_path: Path):
        result = runner.invoke(app, ["strategy", "list", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "No strategy files" in result.output


class TestStrategyPromote:
    def test_promote_valid(self, tmp_path: Path):
        yaml_file = tmp_path / "strategy.yaml"
        yaml_file.write_text(VALID_STRATEGY_YAML)

        result = runner.invoke(app, ["strategy", "promote", str(yaml_file)])
        assert result.exit_code == 0
        assert "Promoted" in result.output

        # Verify status changed in file
        import yaml
        updated = yaml.safe_load(yaml_file.read_text())
        assert updated["status"] == "stable"
```

### tests/test_blueprint.py

```python
"""Tests for qitp blueprint sub-commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_cli.main import app

runner = CliRunner()

VALID_AGENT_YAML = """
agent_id: test-agent
name: Test Agent
version: "1.0.0"
model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
tools:
  - name: market-data
    type: mcp
"""

VALID_STRATEGY_YAML = """
strategy_id: test-strategy
name: Test Strategy
version: "1.0.0"
entry_conditions:
  - type: gap_up
exit_conditions:
  - type: stop_loss
"""

EMPTY_YAML = ""


class TestBlueprintLint:
    def test_lint_valid_agent(self, tmp_path: Path):
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(VALID_AGENT_YAML)

        result = runner.invoke(app, ["blueprint", "lint", str(yaml_file)])
        assert result.exit_code == 0
        assert "PASS" in result.output

    def test_lint_valid_strategy(self, tmp_path: Path):
        yaml_file = tmp_path / "strategy.yaml"
        yaml_file.write_text(VALID_STRATEGY_YAML)

        result = runner.invoke(app, ["blueprint", "lint", str(yaml_file)])
        assert result.exit_code == 0

    def test_lint_file_not_found(self):
        result = runner.invoke(app, ["blueprint", "lint", "/nonexistent.yaml"])
        assert result.exit_code == 1

    def test_lint_empty_yaml(self, tmp_path: Path):
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text(EMPTY_YAML)

        result = runner.invoke(app, ["blueprint", "lint", str(yaml_file)])
        assert result.exit_code == 1
```

### tests/test_graph.py

```python
"""Tests for qitp graph sub-commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_cli.main import app
from agent_cli.graph import _build_ascii_diagram, _build_node_table, _build_edge_table, _build_circuit_breaker_section

runner = CliRunner()

GRAPH_AGENT_YAML = """
agent_id: strategy-evaluator
name: Strategy Evaluator
version: "1.0.0"
model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
multi_agent:
  pattern: graph
  nodes:
    - id: gap_analysis
      agent_ref: gap-detector
      type: agent
    - id: technical_analysis
      agent_ref: technical-analyzer
      type: agent
    - id: sentiment_check
      agent_ref: sentiment-analyzer
      type: agent
    - id: quality_gate
      type: gate
      trip_condition: "confidence < 0.5"
      fallback: abort
    - id: strategy_eval
      agent_ref: strategy-evaluator
      type: agent
  edges:
    - from: gap_analysis
      to: technical_analysis
      label: gap_detected
    - from: gap_analysis
      to: sentiment_check
      label: gap_detected
    - from: technical_analysis
      to: quality_gate
      condition: "signals_ready"
    - from: sentiment_check
      to: quality_gate
      condition: "sentiment_scored"
    - from: quality_gate
      to: strategy_eval
      label: gate_passed
"""


class TestGraphRender:
    def test_render_to_terminal(self, tmp_path: Path):
        yaml_file = tmp_path / "graph_agent.yaml"
        yaml_file.write_text(GRAPH_AGENT_YAML)

        result = runner.invoke(app, ["graph", "render", str(yaml_file)])
        assert result.exit_code == 0

    def test_render_to_file(self, tmp_path: Path):
        yaml_file = tmp_path / "graph_agent.yaml"
        yaml_file.write_text(GRAPH_AGENT_YAML)
        output_file = tmp_path / "graph.md"

        result = runner.invoke(app, ["graph", "render", str(yaml_file), "-o", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()

        content = output_file.read_text()
        assert "Strategy Evaluator" in content
        assert "gap_analysis" in content
        assert "## Nodes" in content
        assert "## Edges" in content
        assert "## Circuit Breakers" in content

    def test_render_file_not_found(self):
        result = runner.invoke(app, ["graph", "render", "/nonexistent.yaml"])
        assert result.exit_code == 1


class TestGraphHelpers:
    def test_build_ascii_diagram_empty(self):
        result = _build_ascii_diagram([], [])
        assert "no nodes" in result

    def test_build_ascii_diagram_simple(self):
        nodes = [
            {"id": "a", "agent_ref": "agent-a", "type": "agent"},
            {"id": "b", "agent_ref": "agent-b", "type": "agent"},
        ]
        edges = [{"from": "a", "to": "b", "label": "next"}]
        result = _build_ascii_diagram(nodes, edges)
        assert "a" in result
        assert "b" in result
        assert "-->" in result

    def test_build_node_table(self):
        nodes = [{"id": "n1", "agent_ref": "ref1", "type": "agent"}]
        table = _build_node_table(nodes)
        assert "n1" in table
        assert "ref1" in table

    def test_build_edge_table(self):
        edges = [{"from": "a", "to": "b", "condition": "ready", "label": "go"}]
        table = _build_edge_table(edges)
        assert "a" in table
        assert "b" in table

    def test_circuit_breaker_none(self):
        nodes = [{"id": "n1", "type": "agent"}]
        assert _build_circuit_breaker_section(nodes) is None

    def test_circuit_breaker_found(self):
        nodes = [{"id": "gate1", "type": "gate", "trip_condition": "x < 0.5", "fallback": "abort"}]
        result = _build_circuit_breaker_section(nodes)
        assert "gate1" in result
        assert "Circuit Breakers" in result
```

## Acceptance Criteria
- [ ] `qitp prompt push/get/list/diff/rollback/promote` all call Prompt Registry API correctly
- [ ] `qitp strategy validate` validates against StrategyBlueprint Pydantic model
- [ ] `qitp strategy list` scans directory and displays table
- [ ] `qitp blueprint lint` auto-detects type and validates
- [ ] `qitp graph render` produces ASCII topology from multi_agent graph YAML
- [ ] Graph output includes node table, edge table, and circuit breaker section
- [ ] All tests pass with mocked API responses

## Test Plan
```bash
cd ~/dev/tccw-agent-cli
pip install -e ".[dev]"
pytest tests/ -v
```

## Agent Instructions
This CLI is the developer's primary interface to the platform. It should feel polished — use Rich for all output formatting. Every command should have clear error messages and exit codes. The `graph render` command is the showpiece: it turns abstract YAML into a visual diagram that developers can paste into docs or PRs. Use httpx with context managers for all API calls. Validate inputs early, fail fast with helpful messages.
