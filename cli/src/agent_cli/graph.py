"""Graph sub-commands: render.

Generates ASCII flow diagrams from multi_agent YAML (graph pattern).
Produces a markdown file with:
- ASCII box diagram showing nodes and arrows
- Table of nodes (id, agent_ref, type)
- Table of edges (from->to, condition, label)
- Circuit breaker section if any gate nodes
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

graph_app = typer.Typer(no_args_is_help=True)
console = Console()


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_adjacency(edges: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """Build adjacency map: source -> list of (target, label)."""
    adjacency: dict[str, list[tuple[str, str]]] = {}
    for edge in edges:
        src = edge.get("from") or edge.get("source", "?")
        tgt = edge.get("to") or edge.get("target", "?")
        adjacency.setdefault(src, []).append((tgt, edge.get("label", "")))
    return adjacency


def _get_node_id(node: dict) -> str:
    return node.get("id", node.get("node_id", "?"))


def _topological_sort(node_ids: list[str], edges: list[dict], adjacency: dict[str, list[tuple[str, str]]]) -> list[str]:
    """BFS topological sort of node IDs."""
    incoming = dict.fromkeys(node_ids, 0)
    for edge in edges:
        tgt = edge.get("to") or edge.get("target", "?")
        if tgt in incoming:
            incoming[tgt] += 1

    queue = deque([nid for nid, cnt in incoming.items() if cnt == 0])
    ordered: list[str] = []
    visited: set[str] = set()
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

    for nid in node_ids:
        if nid not in visited:
            ordered.append(nid)
    return ordered


def _render_node_box(nid: str, node: dict, box_width: int = 30) -> list[str]:
    """Render a single node as ASCII box lines."""
    lines: list[str] = []
    agent_ref = node.get("agent_ref", node.get("type", ""))
    node_type = node.get("type", "agent")

    border = "+" + "-" * (box_width - 2) + "+"
    lines.append(border)
    lines.append("|" + f"  {nid}".ljust(box_width - 2) + "|")
    if agent_ref:
        lines.append("|" + f"  ({agent_ref})".ljust(box_width - 2) + "|")
    if node_type == "gate":
        lines.append("|" + "  [GATE]".ljust(box_width - 2) + "|")
    lines.append(border)
    return lines


def _build_ascii_diagram(nodes: list[dict], edges: list[dict]) -> str:
    """Build an ASCII box-and-arrow diagram from nodes and edges."""
    if not nodes:
        return "(no nodes defined)"

    adjacency = _build_adjacency(edges)
    node_ids = [_get_node_id(n) for n in nodes]
    ordered = _topological_sort(node_ids, edges, adjacency)
    node_map = {_get_node_id(n): n for n in nodes}

    lines: list[str] = []
    for nid in ordered:
        lines.extend(_render_node_box(nid, node_map.get(nid, {})))
        targets = adjacency.get(nid, [])
        if targets:
            for tgt, label in targets:
                arrow = f" --[{label}]--> {tgt}" if label else f" --> {tgt}"
                lines.append(f"    |{arrow}")
            lines.append("    v")

    return "\n".join(lines)


def _build_node_table(nodes: list[dict]) -> str:
    """Build a markdown table of nodes."""
    rows = ["| ID | Agent Ref | Type |", "|---|---|---|"]
    for n in nodes:
        nid = n.get("id", n.get("node_id", "?"))
        agent_ref = n.get("agent_ref", "\u2014")
        node_type = n.get("type", "agent")
        rows.append(f"| {nid} | {agent_ref} | {node_type} |")
    return "\n".join(rows)


def _build_edge_table(edges: list[dict]) -> str:
    """Build a markdown table of edges."""
    rows = ["| From | To | Condition | Label |", "|---|---|---|---|"]
    for e in edges:
        src = e.get("from") or e.get("source", "?")
        tgt = e.get("to") or e.get("target", "?")
        condition = e.get("condition", "\u2014")
        label = e.get("label", "\u2014")
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
        trip = g.get("trip_condition", "\u2014")
        fallback = g.get("fallback", "\u2014")
        lines.append(f"- **{gid}**: trip=`{trip}`, fallback=`{fallback}`")

    return "\n".join(lines)


@graph_app.command("render")
def render(
    agent_yaml_path: Path = typer.Argument(..., help="Path to agent YAML with multi_agent.pattern=graph"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output markdown file path"),
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
        console.print("[yellow]Warning:[/yellow] No nodes defined in multi_agent section.")

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
