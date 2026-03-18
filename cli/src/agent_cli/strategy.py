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

# Default strategies directory — override with AGENT_STRATEGIES_DIR env var
DEFAULT_STRATEGIES_DIR = "blueprints/strategies"


def _get_strategies_dir() -> Path:
    import os
    return Path(os.environ.get("AGENT_STRATEGIES_DIR", DEFAULT_STRATEGIES_DIR))


def _load_yaml(path: Path) -> dict:
    """Load and parse a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _validate_strategy(data: dict) -> tuple[bool, list[str]]:
    """Validate strategy data against StrategyBlueprint Pydantic model.

    Returns (is_valid, list_of_errors).
    """
    try:
        from agent_core.blueprints.strategy import StrategyBlueprint
        StrategyBlueprint.model_validate(data)
        return True, []
    except ImportError:
        # Fallback: basic structural validation if agent-core not installed
        errors = []
        required_fields = [
            "id", "name", "version",
            "entry_conditions", "exit_conditions",
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
            f"[green]VALID[/green] \u2014 {data.get('name', yaml_path.stem)} v{data.get('version', '?')}",
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
                data.get("name", "\u2014"),
                data.get("version", "\u2014"),
                "[green]Y[/green]" if is_valid else "[red]N[/red]",
                (data.get("description", "\u2014") or "\u2014")[:50],
            )
        except Exception as e:
            table.add_row(f.name, "\u2014", "\u2014", "[red]ERR[/red]", str(e)[:50])

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
