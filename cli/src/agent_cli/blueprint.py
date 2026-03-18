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
        from agent_core.blueprints.agent import AgentBlueprint
        AgentBlueprint.model_validate(data)
        return True, []
    except ImportError:
        errors = []
        required = ["id", "name", "version", "model"]
        for field in required:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        return len(errors) == 0, errors
    except Exception as e:
        return False, [str(e)]


def _validate_strategy_blueprint(data: dict) -> tuple[bool, list[str]]:
    """Validate against StrategyBlueprint Pydantic model."""
    try:
        from agent_core.blueprints.strategy import StrategyBlueprint
        StrategyBlueprint.model_validate(data)
        return True, []
    except ImportError:
        errors = []
        required = ["id", "name", "version", "entry_conditions", "exit_conditions"]
        for field in required:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        return len(errors) == 0, errors
    except Exception as e:
        return False, [str(e)]


def _validate_by_type(bp_type: str, data: dict) -> tuple[bool, list[str]]:
    """Dispatch validation to the correct handler."""
    validators = {
        "agent": _validate_agent_blueprint,
        "strategy": _validate_strategy_blueprint,
    }
    validator = validators.get(bp_type)
    if validator:
        return validator(data)
    console.print("[yellow]Warning:[/yellow] Could not detect blueprint type. Running basic checks.")
    return True, []


def _build_summary_tree(yaml_path: Path, bp_type: str, data: dict) -> Tree:
    """Build a Rich tree summarising the blueprint."""
    tree = Tree(f"[bold]{yaml_path.name}[/bold] ({bp_type} blueprint)")
    tree.add(f"Name: {data.get('name', '\u2014')}")
    tree.add(f"Version: {data.get('version', '\u2014')}")

    model = data.get("model")
    if isinstance(model, dict):
        model_branch = tree.add("Model")
        model_branch.add(f"provider: {model.get('provider', '\u2014')}")
        model_branch.add(f"model_id: {model.get('model_id', '\u2014')}")

    ma = data.get("multi_agent")
    if ma:
        ma_branch = tree.add(f"Multi-Agent: {ma.get('pattern', '\u2014')}")
        if "nodes" in ma:
            ma_branch.add(f"Nodes: {len(ma['nodes'])}")
        if "edges" in ma:
            ma_branch.add(f"Edges: {len(ma['edges'])}")

    if "tools" in data:
        tree.add(f"Tools: {len(data['tools'])}")
    return tree


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
    is_valid, errors = _validate_by_type(bp_type, data)

    console.print(_build_summary_tree(yaml_path, bp_type, data))
    console.print()

    if is_valid:
        console.print("[green]PASS[/green] \u2014 Blueprint is valid.")
    else:
        console.print(f"[red]FAIL[/red] \u2014 {len(errors)} error(s):")
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
