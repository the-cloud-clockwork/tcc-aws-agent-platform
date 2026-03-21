"""Typer application entrypoint. Registers all sub-command groups."""

import typer

from agent_cli.blueprint import blueprint_app
from agent_cli.evaluation import eval_app
from agent_cli.generate import generate_app
from agent_cli.graph import graph_app
from agent_cli.prompt import prompt_app

app = typer.Typer(
    name="agentcli",
    help="agentcli — manage prompts, blueprints, and agent graphs.",
    no_args_is_help=True,
)

app.add_typer(prompt_app, name="prompt", help="Prompt registry operations")
app.add_typer(blueprint_app, name="blueprint", help="Blueprint linting and validation")
app.add_typer(graph_app, name="graph", help="Agent graph rendering")
app.add_typer(
    generate_app, name="generate", help="Generate runtime configs and Dockerfiles"
)
app.add_typer(eval_app, name="eval", help="Agent evaluation operations")


@app.callback()
def main_callback() -> None:
    """agentcli — generic agent platform developer CLI."""


if __name__ == "__main__":
    app()
