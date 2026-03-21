"""Evaluation sub-commands: run, status.

Communicates with AgentCore Evaluation via the agent-core SDK.
"""

from __future__ import annotations

import os

import typer
from rich.console import Console
from rich.table import Table

eval_app = typer.Typer(no_args_is_help=True)
console = Console()


def _get_eval_client():  # noqa: ANN202
    """Build an EvaluationClient from environment."""
    from agent_core.evaluation.client import EvaluationClient

    return EvaluationClient(region=os.environ.get("AWS_REGION"))


@eval_app.command("run")
def run(
    agent_id: str = typer.Option(..., "--agent-id", help="AgentCore Runtime agent ID."),
    session_id: str = typer.Option(..., "--session-id", help="Session to evaluate."),
    evaluators: str = typer.Option(
        ...,
        "--evaluators",
        help="Comma-separated evaluator IDs (e.g. Builtin.Correctness,Builtin.GoalSuccessRate).",
    ),
) -> None:
    """Run on-demand evaluation for a specific agent session."""
    evaluator_list = [e.strip() for e in evaluators.split(",") if e.strip()]
    if not evaluator_list:
        console.print("[red]Error:[/red] No evaluators specified.")
        raise typer.Exit(code=1)

    client = _get_eval_client()
    console.print(
        f"Running evaluation: agent=[bold]{agent_id}[/bold] "
        f"session=[bold]{session_id}[/bold] "
        f"evaluators={len(evaluator_list)}"
    )

    try:
        result = client.run(
            agent_id=agent_id,
            session_id=session_id,
            evaluators=evaluator_list,
        )
    except Exception as exc:
        console.print(f"[red]Evaluation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="Evaluation Results")
    table.add_column("Evaluator", style="cyan")
    table.add_column("Label", style="green")
    table.add_column("Score", justify="right")
    table.add_column("Explanation", max_width=60)

    for score in result.scores:
        table.add_row(
            score.evaluator_name,
            score.label,
            f"{score.value:.2f}",
            score.explanation[:60] + "..."
            if len(score.explanation) > 60
            else score.explanation,
        )

    console.print(table)


@eval_app.command("status")
def status(
    agent_id: str = typer.Option(..., "--agent-id", help="AgentCore Runtime agent ID."),
    config_name: str = typer.Option(
        None,
        "--config-name",
        help="Online eval config name. Defaults to {agent_id}_online_eval.",
    ),
) -> None:
    """Check online evaluation status and results."""
    resolved_name = config_name or f"{agent_id}_online_eval"

    client = _get_eval_client()
    console.print(
        f"Fetching online eval status: agent=[bold]{agent_id}[/bold] "
        f"config=[bold]{resolved_name}[/bold]"
    )

    try:
        results = client.get_online_results(
            agent_id=agent_id,
            config_name=resolved_name,
        )
    except Exception as exc:
        console.print(f"[red]Failed to fetch results:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if not results:
        console.print("[yellow]No online evaluation results found.[/yellow]")
        return

    table = Table(title=f"Online Evaluation — {resolved_name}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    for entry in results:
        if isinstance(entry, dict):
            for k, v in entry.items():
                table.add_row(str(k), str(v))
        else:
            table.add_row(str(entry), "—")

    console.print(table)
