"""Deploy sub-command: build, push, and create AgentCore Runtime from a blueprint.

Uses ``bedrock_agentcore_starter_toolkit.Runtime`` to handle the full
lifecycle: Docker build → ECR push → ``create_agent_runtime()`` call.

Reference: TECHNICAL-GUIDE.md section "Deployment CLI — 3-Step Workflow".
"""

from __future__ import annotations

import os
from pathlib import Path

import typer
import yaml
from rich.console import Console

from agent_core.blueprints.agent import AgentBlueprint
from agent_core.runtime.config_gen import generate_agentcore_config, generate_dockerfile

deploy_app = typer.Typer(no_args_is_help=True)
console = Console()


def _load_blueprint(yaml_path: Path) -> AgentBlueprint:
    """Load and validate a blueprint YAML file."""
    if not yaml_path.exists():
        console.print(f"[red]File not found:[/red] {yaml_path}")
        raise typer.Exit(code=1)

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    return AgentBlueprint.model_validate(data)


def _resolve_region(region_override: str | None, env: str) -> str:
    """Resolve AWS region from flag, env var, or fail."""
    region = region_override or os.environ.get("AWS_DEFAULT_REGION", "")
    if not region:
        console.print(
            "[red]AWS region required.[/red] Set --region flag or AWS_DEFAULT_REGION env var."
        )
        raise typer.Exit(code=1)
    return region


@deploy_app.command("agent")
def deploy_agent(
    yaml_path: Path = typer.Argument(..., help="Path to agent blueprint YAML"),
    env: str = typer.Option(
        "dev", "--env", "-e", help="Target environment (dev, staging, production)"
    ),
    region: str | None = typer.Option(
        None, "--region", "-r", help="AWS region (defaults to AWS_DEFAULT_REGION)"
    ),
    entrypoint: str = typer.Option(
        "app.py", "--entrypoint", help="Python entrypoint file"
    ),
    requirements: str = typer.Option(
        "requirements.txt", "--requirements", help="Requirements file"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Generate artifacts only, don't deploy"
    ),
) -> None:
    """Deploy an agent to AgentCore Runtime.

    Reads the blueprint YAML, generates deployment artifacts (Dockerfile,
    .bedrock_agentcore.yaml), then uses the AgentCore starter toolkit to
    build the container, push to ECR, and create the Runtime.
    """
    blueprint = _load_blueprint(yaml_path)
    aws_region = _resolve_region(region, env)

    console.print(f"[bold]Deploying agent:[/bold] {blueprint.id} v{blueprint.version}")
    console.print(f"  Environment: {env}")
    console.print(f"  Region:      {aws_region}")
    console.print(f"  Runtime:     {blueprint.runtime.type}")

    # Step 1: Generate .bedrock_agentcore.yaml
    agentcore_config = generate_agentcore_config(blueprint, entrypoint_file=entrypoint)
    config_path = Path(".bedrock_agentcore.yaml")
    config_path.write_text(agentcore_config)
    console.print(f"  [green]Generated:[/green] {config_path}")

    # Step 2: Generate Dockerfile
    dockerfile_content = generate_dockerfile(
        blueprint,
        base_image="python:3.12-slim",
        requirements_file=requirements,
    )
    dockerfile_path = Path("Dockerfile")
    dockerfile_path.write_text(dockerfile_content)
    console.print(f"  [green]Generated:[/green] {dockerfile_path}")

    if dry_run:
        console.print(
            "\n[yellow]Dry run complete.[/yellow] Artifacts generated, no deployment."
        )
        return

    # Step 3: Deploy via bedrock_agentcore_starter_toolkit
    try:
        from bedrock_agentcore_starter_toolkit import Runtime  # type: ignore[import-untyped]
    except ImportError:
        console.print(
            "[red]bedrock_agentcore_starter_toolkit not installed.[/red]\n"
            "Install it: pip install bedrock-agentcore-starter-toolkit"
        )
        raise typer.Exit(code=1)

    rt = Runtime()
    configure_kwargs: dict = {
        "entrypoint": entrypoint,
        "auto_create_execution_role": True,
        "auto_create_ecr": True,
        "requirements_file": requirements,
        "region": aws_region,
        "agent_name": blueprint.id,
    }

    # Wire authorizer if declared
    if blueprint.identity.authorizer:
        auth = blueprint.identity.authorizer
        if auth.type.value == "cognito_jwt" and auth.user_pool_id:
            pool_id = os.path.expandvars(auth.user_pool_id)
            client_id = os.path.expandvars(auth.client_id or "")
            discovery_url = (
                f"https://cognito-idp.{aws_region}.amazonaws.com/{pool_id}"
                "/.well-known/openid-configuration"
            )
            configure_kwargs["authorizer_configuration"] = {
                "customJWTAuthorizer": {
                    "discoveryUrl": discovery_url,
                    "allowedClients": [client_id] if client_id else [],
                }
            }
        elif auth.type.value == "custom_jwt" and auth.discovery_url:
            configure_kwargs["authorizer_configuration"] = {
                "customJWTAuthorizer": {
                    "discoveryUrl": os.path.expandvars(auth.discovery_url),
                    "allowedClients": [
                        os.path.expandvars(c) for c in auth.allowed_clients
                    ],
                }
            }

    # Wire network mode if private
    if blueprint.runtime.network_mode == "PRIVATE":
        configure_kwargs["network_mode"] = "PRIVATE"

    console.print("\n[bold]Launching AgentCore Runtime...[/bold]")
    rt.configure(**configure_kwargs)
    rt.launch()

    console.print("[green]Deployment complete![/green]")

    # Print status
    try:
        status = rt.status()
        console.print(f"  Status: {status}")
    except Exception:
        console.print(
            "  [yellow]Status check unavailable (runtime may still be initializing).[/yellow]"
        )
