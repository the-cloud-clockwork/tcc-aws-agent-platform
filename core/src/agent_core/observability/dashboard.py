"""CloudWatch GenAI Observability dashboard generation.

Generates a CloudWatch dashboard JSON body with GenAI-specific widgets:
invocation counts, LLM latency, token usage, tool call metrics, and errors.

The dashboard is deployed via the CloudWatch API at agent startup or
via ``agentcli generate dashboard``.
"""

from __future__ import annotations

import json
import logging
import boto3

from agent_core.schemas.observability_config import DashboardConfig

logger = logging.getLogger(__name__)


def _metric_widget(
    title: str,
    namespace: str,
    metrics: list[list[str]],
    *,
    stat: str = "Sum",
    period: int = 300,
    width: int = 12,
    height: int = 6,
) -> dict:
    """Build a single CloudWatch metric widget."""
    return {
        "type": "metric",
        "width": width,
        "height": height,
        "properties": {
            "title": title,
            "namespace": namespace,
            "metrics": metrics,
            "stat": stat,
            "period": period,
            "view": "timeSeries",
            "stacked": False,
            "region": "${AWS::Region}",
        },
    }


def _log_widget(
    title: str,
    log_group: str,
    query: str,
    *,
    width: int = 24,
    height: int = 6,
) -> dict:
    """Build a CloudWatch Logs Insights query widget."""
    return {
        "type": "log",
        "width": width,
        "height": height,
        "properties": {
            "title": title,
            "query": f"SOURCE '{log_group}' | {query}",
            "view": "table",
            "region": "${AWS::Region}",
        },
    }


def generate_dashboard_body(agent_name: str, config: DashboardConfig) -> dict:
    """Generate a CloudWatch dashboard JSON body for GenAI agent observability.

    Widgets include:
      - Row 1: Agent invocation count + latency (p50, p99)
      - Row 2: Token usage (input/output tokens)
      - Row 3: Tool call frequency and latency
      - Row 4: Error rate
      - Row 5: Custom metrics (if configured)

    Args:
        agent_name: Agent identifier (used in metric dimensions).
        config: Dashboard configuration from the blueprint.

    Returns:
        Dashboard body dict ready for ``cloudwatch.put_dashboard()``.
    """
    ns = config.metric_namespace
    log_group = f"{config.log_group_prefix}{agent_name}"
    dim = ["AgentName", agent_name]

    widgets: list[dict] = []

    widgets.append(
        _metric_widget(
            "Agent Invocations",
            ns,
            [
                [ns, "Invocations", *dim],
                [ns, "SuccessfulInvocations", *dim],
                [ns, "FailedInvocations", *dim],
            ],
        )
    )

    widgets.append(
        _metric_widget(
            "Invocation Latency",
            ns,
            [
                [ns, "InvocationLatency", *dim],
            ],
            stat="p50",
        )
    )

    widgets.append(
        _metric_widget(
            "Token Usage",
            ns,
            [
                [ns, "InputTokens", *dim],
                [ns, "OutputTokens", *dim],
                [ns, "TotalTokens", *dim],
            ],
        )
    )

    widgets.append(
        _metric_widget(
            "Estimated Cost (USD)",
            ns,
            [
                [ns, "EstimatedCostUSD", *dim],
            ],
            stat="Sum",
        )
    )

    widgets.append(
        _metric_widget(
            "Tool Calls",
            ns,
            [
                [ns, "ToolInvocations", *dim],
                [ns, "ToolErrors", *dim],
            ],
        )
    )

    widgets.append(
        _metric_widget(
            "Tool Latency",
            ns,
            [
                [ns, "ToolLatency", *dim],
            ],
            stat="p99",
        )
    )

    widgets.append(
        _metric_widget(
            "Error Rate",
            ns,
            [
                [ns, "Errors", *dim],
            ],
        )
    )

    widgets.append(
        _log_widget(
            "Recent Errors",
            log_group,
            "filter @message like /ERROR/ | sort @timestamp desc | limit 20",
        )
    )

    for metric_name in config.custom_metrics:
        widgets.append(
            _metric_widget(
                metric_name,
                ns,
                [[ns, metric_name, *dim]],
            )
        )

    return {"widgets": widgets}


def deploy_dashboard(
    agent_name: str,
    config: DashboardConfig,
    *,
    region: str | None = None,
) -> str:
    """Deploy a GenAI observability dashboard via the CloudWatch API.

    Creates or updates the dashboard. Region is resolved from
    ``AWS_DEFAULT_REGION`` if not provided (never hardcoded).

    Args:
        agent_name: Agent identifier.
        config: Dashboard configuration from the blueprint.
        region: AWS region override.

    Returns:
        The dashboard name.
    """
    dashboard_name = f"{agent_name}-genai-observability"
    body = generate_dashboard_body(agent_name, config)

    client = boto3.client("cloudwatch", region_name=region)
    client.put_dashboard(
        DashboardName=dashboard_name,
        DashboardBody=json.dumps(body),
    )
    logger.info("Deployed dashboard %s", dashboard_name)
    return dashboard_name
