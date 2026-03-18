"""Shared pytest fixtures for agent-core tests."""
from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest
import yaml

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Sample YAML content
# ---------------------------------------------------------------------------

SAMPLE_AGENT_YAML = textwrap.dedent("""\
    id: gap_detector
    version: "1.2.0"
    name: Gap Detection Agent
    description: Scans watchlist for significant Friday/Monday price gaps
    model:
      provider: bedrock
      model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
      temperature: 0.2
      max_tokens: 4096
      cache_prompt: default
      cache_tools: default
    prompt_ref: gap_detector_v1.2
    tools:
      - mcp: data-mcp
        tools: [get_watchlist_gaps, get_data, get_volume_profile]
      - mcp: artifacts-mcp
        tools: [create_artifact]
    runtime:
      type: agentcore
      max_iterations: 5
      max_execution_time: 120
    execution_modes:
      simulation: true
      staging: true
      production: true
    output_schema: gap_detection_output_v1
    hooks:
      - ObservabilityHook
    multi_agent:
      pattern: swarm
      execution_timeout: 90
      node_timeout: 30
      max_handoffs: 20
""")

SAMPLE_STRATEGY_YAML = textwrap.dedent("""\
    id: gap_momentum_up
    version: "1.0.0"
    name: Gap Momentum Up
    description: Process data with analytics confirmation
    asset_types: [stock, etf]
    scopes: [US, EU, ES]
    required_signals: [data, analytics]
    entry_conditions:
      logic: AND
      conditions:
        - field: gap_pct
          op: gte
          value: 2.0
        - field: sentiment_score
          op: gte
          value: 0.60
    exit_conditions:
      logic: OR
      conditions:
        - type: trailing_stop
        - field: holding_days
          op: gte
          value: 5
    max_concurrent_positions: 3
    required_agents: [gap_detector, sentiment_analyzer, portfolio_recommender]
    required_mcps: [data-mcp, analytics-mcp, executor-mcp]
""")

SAMPLE_WORKFLOW_YAML = textwrap.dedent("""\
    id: weekly_gap_analysis
    version: "1.0.0"
    name: Weekly Gap Analysis Pipeline
    trigger:
      type: schedule
      schedule: "cron(30 8 ? * MON *)"
      timezone: Europe/Madrid
    timeout_minutes: 60
    states:
      - id: ValidateSchedule
        type: task
        lambda_ref: schedule-validator
        result_path: $.calendar
        next: CheckScheduleActive
      - id: CheckScheduleActive
        type: choice
        choices:
          - condition:
              path: $.calendar.is_active_day
              op: eq
              value: false
            next: NoOpComplete
        default: FetchWatchlistGaps
""")


@pytest.fixture()
def tmp_blueprints(tmp_path: Path) -> Path:
    """Create a temporary blueprints directory with sample YAML files.

    Directory layout::

        tmp_path/
        ├── agents/
        │   └── gap_detector.yaml
        ├── strategies/
        │   └── gap_momentum_up.yaml
        └── workflows/
            └── weekly_gap_analysis.yaml
    """
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "gap_detector.yaml").write_text(SAMPLE_AGENT_YAML)

    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir()
    (strategies_dir / "gap_momentum_up.yaml").write_text(SAMPLE_STRATEGY_YAML)

    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    (workflows_dir / "weekly_gap_analysis.yaml").write_text(SAMPLE_WORKFLOW_YAML)

    return tmp_path


@pytest.fixture()
def sample_agent_dict() -> dict:
    """Parsed dict from the sample agent YAML."""
    return yaml.safe_load(SAMPLE_AGENT_YAML)


@pytest.fixture()
def sample_strategy_dict() -> dict:
    """Parsed dict from the sample strategy YAML."""
    return yaml.safe_load(SAMPLE_STRATEGY_YAML)


@pytest.fixture()
def tmp_prompts(tmp_path: Path) -> Path:
    """Create a temp directory with local prompt files."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "gap_detector_v1.2.txt").write_text(
        "You are a gap detection agent. Analyse price gaps."
    )
    (prompts_dir / "gap_detector.txt").write_text(
        "You are a gap detection agent (latest). Analyse price gaps."
    )
    return prompts_dir
