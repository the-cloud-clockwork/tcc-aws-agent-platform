"""Policy sub-commands: lint, generate.

Validates and translates Cedar policy rules from blueprint YAML.
"""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.syntax import Syntax

policy_app = typer.Typer(no_args_is_help=True)
console = Console()


@policy_app.command("lint")
def lint(
    path: Path = typer.Argument(..., help="Path to a blueprint YAML file."),
) -> None:
    """Validate the ``policy:`` block in a blueprint YAML file."""
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {path}")
        raise typer.Exit(code=1)

    with open(path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        console.print("[red]Error:[/red] YAML root must be a mapping.")
        raise typer.Exit(code=1)

    policy_data = data.get("policy")
    if not policy_data:
        console.print("[yellow]No 'policy:' block found in blueprint.[/yellow]")
        raise typer.Exit(code=0)

    from pydantic import ValidationError

    from agent_core.schemas.policy_config import PolicyConfig

    try:
        config = PolicyConfig(**policy_data)
    except ValidationError as exc:
        console.print("[red]Validation errors:[/red]")
        for error in exc.errors():
            loc = " → ".join(str(part) for part in error["loc"])
            console.print(f"  {loc}: {error['msg']}")
        raise typer.Exit(code=1)

    console.print(
        f"[green]Policy config valid:[/green] engine={config.engine}, mode={config.mode}"
    )
    console.print(f"  Rules: {len(config.rules)}")

    if config.rules:
        from agent_core.policy.translator import (
            translate_rules,
            validate_cedar_expression,
        )

        gateway_arn = "<GATEWAY_ARN>"
        cedar = translate_rules(config.rules, gateway_arn, config.target_prefix)

        for rule in config.rules:
            for condition in (rule.when, rule.unless):
                if condition:
                    errors = validate_cedar_expression(condition)
                    if errors:
                        console.print(
                            f"  [yellow]Warning in rule '{rule.name}':[/yellow]"
                        )
                        for err in errors:
                            console.print(f"    {err}")

        console.print("\n[bold]Generated Cedar (preview):[/bold]")
        console.print(Syntax(cedar, "cedar", theme="monokai"))


@policy_app.command("generate")
def generate(
    path: Path = typer.Argument(..., help="Path to a blueprint YAML file."),
    gateway_arn: str = typer.Option(
        ..., "--gateway-arn", help="Gateway ARN for the resource clause."
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Output file (stdout if not set)."
    ),
) -> None:
    """Translate blueprint policy rules into Cedar and output them."""
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {path}")
        raise typer.Exit(code=1)

    with open(path) as f:
        data = yaml.safe_load(f)

    policy_data = data.get("policy")
    if not policy_data:
        console.print("[red]Error:[/red] No 'policy:' block in blueprint.")
        raise typer.Exit(code=1)

    from pydantic import ValidationError

    from agent_core.schemas.policy_config import PolicyConfig

    try:
        config = PolicyConfig(**policy_data)
    except ValidationError as exc:
        console.print("[red]Validation errors:[/red]")
        for error in exc.errors():
            loc = " → ".join(str(part) for part in error["loc"])
            console.print(f"  {loc}: {error['msg']}")
        raise typer.Exit(code=1)

    from agent_core.policy.translator import translate_rules

    cedar = translate_rules(config.rules, gateway_arn, config.target_prefix)

    if not cedar:
        console.print("[yellow]No rules to translate.[/yellow]")
        raise typer.Exit(code=0)

    if output:
        output.write_text(cedar)
        console.print(f"[green]Cedar written to {output}[/green]")
    else:
        console.print(Syntax(cedar, "cedar", theme="monokai"))
