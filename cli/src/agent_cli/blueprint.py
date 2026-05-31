"""Blueprint sub-commands: lint, validate.

Validates blueprint YAML (agent or workflow) against agent-core models.
"""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.tree import Tree

blueprint_app = typer.Typer(no_args_is_help=True)
console = Console()


def _detect_blueprint_type(data: dict) -> str:
    """Detect whether a YAML is an agent, strategy, or workflow blueprint."""
    if "model" in data or "prompt_ref" in data or "gateway" in data:
        return "agent"
    if "required_signals" in data or "entry_conditions" in data or "exit_conditions" in data:
        return "strategy"
    if "states" in data or ("trigger" in data and "states" in data):
        return "workflow"
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
        for field in ["id", "name", "version"]:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        return len(errors) == 0, errors
    except Exception as e:
        return False, [str(e)]


def _validate_workflow_blueprint(data: dict) -> tuple[bool, list[str]]:
    """Validate against WorkflowBlueprint Pydantic model."""
    try:
        from agent_core.blueprints.workflow import WorkflowBlueprint
        WorkflowBlueprint.model_validate(data)
        return True, []
    except ImportError:
        errors = []
        for field in ["id", "version", "states"]:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        return len(errors) == 0, errors
    except Exception as e:
        return False, [str(e)]


def _cross_validate_agent(data: dict) -> list[str]:
    """Cross-block validation warnings for agent blueprints."""
    warnings: list[str] = []
    if data.get("policy") and data["policy"].get("rules") and not data.get("gateway"):
        warnings.append("Policy rules declared but no gateway configured (policies need Gateway)")
    if data.get("memory") and data["memory"].get("strategies"):
        rt = data.get("runtime", {})
        if rt.get("type") and rt["type"] != "agentcore":
            warnings.append("Memory strategies require runtime.type: agentcore")
    ma = data.get("multi_agent")
    if ma and ma.get("role") == "coordinator" and not ma.get("nodes"):
        warnings.append("Coordinator role declared but no multi_agent.nodes defined")
    if data.get("evaluation") and data["evaluation"].get("online") and not data.get("observability"):
        warnings.append("Online evaluation configured but no observability block (evaluation reads OTEL traces)")
    return warnings


def _report_block_coverage(data: dict) -> list[tuple[str, bool]]:
    """Report which blocks are configured in an agent blueprint."""
    blocks = [
        ("runtime", bool(data.get("runtime"))),
        ("gateway", bool(data.get("gateway"))),
        ("identity", bool(data.get("identity") and (data["identity"].get("authorizer") or data["identity"].get("credentials")))),
        ("memory", bool(data.get("memory") and data["memory"].get("strategies"))),
        ("tools", bool(data.get("tools"))),
        ("observability", bool(data.get("observability"))),
        ("evaluation", bool(data.get("evaluation") and (data["evaluation"].get("online") or data["evaluation"].get("custom_evaluators")))),
        ("policy", bool(data.get("policy") and data["policy"].get("rules"))),
        ("multi_agent", bool(data.get("multi_agent"))),
    ]
    return blocks


def _validate_by_type(bp_type: str, data: dict) -> tuple[bool, list[str]]:
    """Dispatch validation to the correct handler."""
    validators = {
        "agent": _validate_agent_blueprint,
        "strategy": _validate_strategy_blueprint,
        "workflow": _validate_workflow_blueprint,
    }
    validator = validators.get(bp_type)
    if validator:
        return validator(data)
    console.print("[yellow]Warning:[/yellow] Could not detect blueprint type. Running basic checks.")
    return True, []


_EM_DASH = "—"  # em-dash placeholder; kept out of f-strings for the py311 ruff target


def _build_summary_tree(yaml_path: Path, bp_type: str, data: dict) -> Tree:
    """Build a Rich tree summarising the blueprint."""
    tree = Tree(f"[bold]{yaml_path.name}[/bold] ({bp_type} blueprint)")
    tree.add(f"Name: {data.get('name', _EM_DASH)}")
    tree.add(f"Version: {data.get('version', _EM_DASH)}")

    model = data.get("model")
    if isinstance(model, dict):
        model_branch = tree.add("Model")
        model_branch.add(f"provider: {model.get('provider', _EM_DASH)}")
        model_branch.add(f"model_id: {model.get('model_id', _EM_DASH)}")

    ma = data.get("multi_agent")
    if ma:
        ma_branch = tree.add(f"Multi-Agent: {ma.get('pattern', _EM_DASH)}")
        if "nodes" in ma:
            ma_branch.add(f"Nodes: {len(ma['nodes'])}")
        if "edges" in ma:
            ma_branch.add(f"Edges: {len(ma['edges'])}")

    if "tools" in data:
        tree.add(f"Tools: {len(data['tools'])}")

    # Block coverage for agent blueprints
    if bp_type == "agent":
        blocks_branch = tree.add("[bold]Block Coverage[/bold]")
        for block_name, present in _report_block_coverage(data):
            icon = "[green]\u2713[/green]" if present else "[dim]\u2014[/dim]"
            blocks_branch.add(f"{icon} {block_name}")

    return tree


@blueprint_app.command("lint")
def lint(
    yaml_path: Path = typer.Argument(..., help="Path to blueprint YAML file"),
) -> None:
    """Lint and validate a blueprint YAML file.

    Auto-detects the blueprint type and validates against the appropriate
    Pydantic schema.
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

    # Cross-block validation warnings (agent only)
    if bp_type == "agent" and is_valid:
        warnings = _cross_validate_agent(data)
        if warnings:
            console.print("[yellow]Warnings:[/yellow]")
            for w in warnings:
                console.print(f"  [yellow]![/yellow] {w}")
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
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)
