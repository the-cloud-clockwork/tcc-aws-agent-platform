"""Generate sub-commands: runtime-config, dockerfile.

Produces .bedrock_agentcore.yaml and Dockerfile from agent blueprint YAML.
"""
from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.console import Console

from agent_core.blueprints.agent import AgentBlueprint
from agent_core.runtime.config_gen import generate_agentcore_config, generate_dockerfile

generate_app = typer.Typer(no_args_is_help=True)
console = Console()


def _load_blueprint(yaml_path: Path) -> AgentBlueprint:
    """Load and validate a blueprint YAML file."""
    if not yaml_path.exists():
        console.print(f"[red]File not found:[/red] {yaml_path}")
        raise typer.Exit(code=1)

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    return AgentBlueprint.model_validate(data)


@generate_app.command("runtime-config")
def runtime_config(
    yaml_path: Path = typer.Argument(..., help="Path to agent blueprint YAML"),
    output_dir: Path = typer.Option(".", "--output-dir", "-o", help="Output directory"),
    entrypoint: str = typer.Option("app.py", "--entrypoint", "-e", help="Python entrypoint file"),
) -> None:
    """Generate .bedrock_agentcore.yaml from a blueprint YAML."""
    blueprint = _load_blueprint(yaml_path)
    content = generate_agentcore_config(blueprint, entrypoint_file=entrypoint)

    output_file = output_dir / ".bedrock_agentcore.yaml"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(content)

    console.print(f"[green]Generated:[/green] {output_file}")


@generate_app.command("dockerfile")
def dockerfile(
    yaml_path: Path = typer.Argument(..., help="Path to agent blueprint YAML"),
    output_dir: Path = typer.Option(".", "--output-dir", "-o", help="Output directory"),
    base_image: str = typer.Option("python:3.12-slim", "--base-image", help="Docker base image"),
    requirements: str = typer.Option("requirements.txt", "--requirements", "-r", help="Requirements file"),
) -> None:
    """Generate Dockerfile from a blueprint YAML."""
    blueprint = _load_blueprint(yaml_path)
    content = generate_dockerfile(
        blueprint,
        base_image=base_image,
        requirements_file=requirements,
    )

    output_file = output_dir / "Dockerfile"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(content)

    console.print(f"[green]Generated:[/green] {output_file}")
