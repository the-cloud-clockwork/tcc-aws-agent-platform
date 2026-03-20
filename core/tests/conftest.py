"""Shared pytest fixtures for agent-core tests."""
from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
import yaml

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Sample YAML content
# ---------------------------------------------------------------------------

SAMPLE_AGENT_YAML = textwrap.dedent("""\
    id: test_detector
    version: "1.2.0"
    name: Test Detection Agent
    description: Scans data sources for significant anomalies
    model:
      provider: bedrock
      model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
      temperature: 0.2
      max_tokens: 4096
      cache_prompt: default
      cache_tools: default
    prompt_ref: test_detector_v1.2
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
    output_schema: test_detection_output_v1
    hooks:
      - ObservabilityHook
""")

SAMPLE_STRATEGY_YAML = textwrap.dedent("""\
    id: multi_signal_entry
    version: "1.0.0"
    name: Multi Signal Entry
    description: Process data with analytics confirmation
    asset_types: [default]
    scopes: [global]
    required_signals: [data, analytics]
    entry_conditions:
      logic: AND
      conditions:
        - field: score_a
          op: gte
          value: 2.0
        - field: score_b
          op: gte
          value: 0.60
    exit_conditions:
      logic: OR
      conditions:
        - type: threshold_breach
        - field: elapsed_time
          op: gte
          value: 5
    max_concurrent_positions: 3
    required_agents: [detector, analyzer, recommender]
    required_mcps: [data-mcp, analytics-mcp, executor-mcp]
""")

SAMPLE_WORKFLOW_YAML = textwrap.dedent("""\
    id: example_workflow
    version: "1.0.0"
    name: Weekly Analysis Pipeline
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
        default: FetchData
""")


@pytest.fixture()
def tmp_blueprints(tmp_path: Path) -> Path:
    """Create a temporary blueprints directory with sample YAML files.

    Directory layout::

        tmp_path/
        ├── agents/
        │   └── test_detector.yaml
        ├── strategies/
        │   └── multi_signal_entry.yaml
        └── workflows/
            └── example_workflow.yaml
    """
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test_detector.yaml").write_text(SAMPLE_AGENT_YAML)

    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir()
    (strategies_dir / "multi_signal_entry.yaml").write_text(SAMPLE_STRATEGY_YAML)

    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    (workflows_dir / "example_workflow.yaml").write_text(SAMPLE_WORKFLOW_YAML)

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
    (prompts_dir / "test_detector_v1.2.txt").write_text(
        "You are a test detection agent. Analyse data anomalies."
    )
    (prompts_dir / "test_detector.txt").write_text(
        "You are a test detection agent (latest). Analyse data anomalies."
    )
    return prompts_dir


@pytest.fixture()
def mock_mcp_factory():
    """Factory returning mock MCP clients with context manager protocol."""

    def factory(name: str, tool_filter: list[str] | None = None):
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.name = name
        client.tool_filter = tool_filter
        return client

    return factory


SAMPLE_SWARM_AGENT_YAML = textwrap.dedent("""\
    id: swarm_agent
    version: "1.0.0"
    name: Swarm Test Agent
    description: Agent with swarm multi-agent config
    model:
      provider: bedrock
      model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
      temperature: 0.2
      max_tokens: 4096
    prompt_ref: test_detector_v1.2
    tools:
      - mcp: data-mcp
        tools: [get_data]
    execution_modes:
      simulation: true
      staging: true
      production: true
    multi_agent:
      pattern: swarm
      execution_timeout: 60
      node_timeout: 20
      max_handoffs: 10
""")

SAMPLE_GRAPH_AGENT_YAML = textwrap.dedent("""\
    id: graph_agent
    version: "1.0.0"
    name: Graph Test Agent
    description: Agent with graph multi-agent config
    model:
      provider: bedrock
      model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
      temperature: 0.2
      max_tokens: 4096
    prompt_ref: test_detector_v1.2
    tools:
      - mcp: data-mcp
        tools: [get_data]
    execution_modes:
      simulation: true
      staging: true
      production: true
    multi_agent:
      pattern: graph
      execution_timeout: 90
      node_timeout: 30
      max_handoffs: 20
""")

SAMPLE_SINGLE_AGENT_YAML = textwrap.dedent("""\
    id: single_agent
    version: "1.0.0"
    name: Single Test Agent
    description: Agent with no multi-agent config
    model:
      provider: bedrock
      model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
      temperature: 0.2
      max_tokens: 4096
    prompt_ref: test_detector_v1.2
    tools:
      - mcp: data-mcp
        tools: [get_data]
    execution_modes:
      simulation: true
      staging: true
      production: true
""")


@pytest.fixture()
def tmp_multi_agent_blueprints(tmp_path: Path, tmp_prompts: Path) -> Path:
    """Create a temporary blueprints dir with swarm, graph, and single agent YAMLs."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "swarm_agent.yaml").write_text(SAMPLE_SWARM_AGENT_YAML)
    (agents_dir / "graph_agent.yaml").write_text(SAMPLE_GRAPH_AGENT_YAML)
    (agents_dir / "single_agent.yaml").write_text(SAMPLE_SINGLE_AGENT_YAML)
    return tmp_path


@pytest.fixture()
def sample_hook_registry():
    """Maps hook names to mock hook classes."""
    mock_hook_cls = MagicMock()
    mock_hook_cls.return_value = MagicMock()  # instance
    return {"ObservabilityHook": mock_hook_cls}


@pytest.fixture()
def sample_schema_registry():
    """Maps schema names to Pydantic models."""
    from pydantic import BaseModel

    class TestOutput(BaseModel):
        result: str
        score: float

    return {"TestOutput": TestOutput}


# ---------------------------------------------------------------------------
# Multi-node graph/swarm YAML fixtures (Phase 5)
# ---------------------------------------------------------------------------

SAMPLE_NODE_A_YAML = textwrap.dedent("""\
    id: node_a
    version: "1.0.0"
    name: Node A Agent
    description: First node in multi-node graph
    model:
      provider: bedrock
      model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
      temperature: 0.2
      max_tokens: 4096
    prompt_ref: test_detector_v1.2
    tools:
      - mcp: data-mcp
        tools: [get_data]
    execution_modes:
      simulation: true
      staging: true
      production: true
""")

SAMPLE_NODE_B_YAML = textwrap.dedent("""\
    id: node_b
    version: "1.0.0"
    name: Node B Agent
    description: Second node in multi-node graph
    model:
      provider: bedrock
      model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
      temperature: 0.2
      max_tokens: 4096
    prompt_ref: test_detector_v1.2
    tools:
      - mcp: data-mcp
        tools: [get_data]
    execution_modes:
      simulation: true
      staging: true
      production: true
""")

SAMPLE_MULTI_NODE_GRAPH_YAML = textwrap.dedent("""\
    id: multi_graph_agent
    version: "1.0.0"
    name: Multi-Node Graph Agent
    description: Agent orchestrating a multi-node graph
    model:
      provider: bedrock
      model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
      temperature: 0.2
      max_tokens: 4096
    prompt_ref: test_detector_v1.2
    tools:
      - mcp: data-mcp
        tools: [get_data]
    execution_modes:
      simulation: true
      staging: true
      production: true
    multi_agent:
      pattern: graph
      execution_timeout: 120
      node_timeout: 45
      max_handoffs: 15
      entry_point: analyze
      nodes:
        - agent_ref: node_a
          node_id: analyze
        - agent_ref: node_b
          node_id: evaluate
      edges:
        - from_node: analyze
          to_node: evaluate
""")

SAMPLE_MULTI_NODE_SWARM_YAML = textwrap.dedent("""\
    id: multi_swarm_agent
    version: "1.0.0"
    name: Multi-Node Swarm Agent
    description: Agent orchestrating a multi-node swarm
    model:
      provider: bedrock
      model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
      temperature: 0.2
      max_tokens: 4096
    prompt_ref: test_detector_v1.2
    tools:
      - mcp: data-mcp
        tools: [get_data]
    execution_modes:
      simulation: true
      staging: true
      production: true
    multi_agent:
      pattern: swarm
      execution_timeout: 90
      node_timeout: 30
      max_handoffs: 20
      max_iterations: 15
      entry_point: detector
      nodes:
        - agent_ref: node_a
          node_id: detector
        - agent_ref: node_b
          node_id: analyzer
""")


@pytest.fixture()
def tmp_multi_node_blueprints(tmp_path: Path, tmp_prompts: Path) -> Path:
    """Create a temporary blueprints dir with multi-node graph/swarm YAMLs."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    (agents_dir / "node_a.yaml").write_text(SAMPLE_NODE_A_YAML)
    (agents_dir / "node_b.yaml").write_text(SAMPLE_NODE_B_YAML)
    (agents_dir / "multi_graph_agent.yaml").write_text(SAMPLE_MULTI_NODE_GRAPH_YAML)
    (agents_dir / "multi_swarm_agent.yaml").write_text(SAMPLE_MULTI_NODE_SWARM_YAML)
    return tmp_path
