"""Tests for agent_cli graph sub-commands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from agent_cli.graph import _build_ascii_diagram, _build_circuit_breaker_section, _build_edge_table, _build_node_table
from agent_cli.main import app

runner = CliRunner()

GRAPH_AGENT_YAML = """
agent_id: strategy-evaluator
name: Strategy Evaluator
version: "1.0.0"
model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
multi_agent:
  pattern: graph
  nodes:
    - id: data_analysis
      agent_ref: my-agent
      type: agent
    - id: technical_analysis
      agent_ref: technical-analyzer
      type: agent
    - id: analytics_check
      agent_ref: analytics-agent
      type: agent
    - id: quality_gate
      type: gate
      trip_condition: "confidence < 0.5"
      fallback: abort
    - id: strategy_eval
      agent_ref: strategy-evaluator
      type: agent
  edges:
    - from: data_analysis
      to: technical_analysis
      label: threshold_detected
    - from: data_analysis
      to: analytics_check
      label: threshold_detected
    - from: technical_analysis
      to: quality_gate
      condition: "signals_ready"
    - from: analytics_check
      to: quality_gate
      condition: "analytics_scored"
    - from: quality_gate
      to: strategy_eval
      label: gate_passed
"""


class TestGraphRender:
    def test_render_to_terminal(self, tmp_path: Path):
        yaml_file = tmp_path / "graph_agent.yaml"
        yaml_file.write_text(GRAPH_AGENT_YAML)

        result = runner.invoke(app, ["graph", "render", str(yaml_file)])
        assert result.exit_code == 0

    def test_render_to_file(self, tmp_path: Path):
        yaml_file = tmp_path / "graph_agent.yaml"
        yaml_file.write_text(GRAPH_AGENT_YAML)
        output_file = tmp_path / "graph.md"

        result = runner.invoke(app, ["graph", "render", str(yaml_file), "-o", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()

        content = output_file.read_text()
        assert "Strategy Evaluator" in content
        assert "data_analysis" in content
        assert "## Nodes" in content
        assert "## Edges" in content
        assert "## Circuit Breakers" in content

    def test_render_file_not_found(self):
        result = runner.invoke(app, ["graph", "render", "/nonexistent.yaml"])
        assert result.exit_code == 1


class TestGraphHelpers:
    def test_build_ascii_diagram_empty(self):
        result = _build_ascii_diagram([], [])
        assert "no nodes" in result

    def test_build_ascii_diagram_simple(self):
        nodes = [
            {"id": "a", "agent_ref": "agent-a", "type": "agent"},
            {"id": "b", "agent_ref": "agent-b", "type": "agent"},
        ]
        edges = [{"from": "a", "to": "b", "label": "next"}]
        result = _build_ascii_diagram(nodes, edges)
        assert "a" in result
        assert "b" in result
        assert "-->" in result

    def test_build_node_table(self):
        nodes = [{"id": "n1", "agent_ref": "ref1", "type": "agent"}]
        table = _build_node_table(nodes)
        assert "n1" in table
        assert "ref1" in table

    def test_build_edge_table(self):
        edges = [{"from": "a", "to": "b", "condition": "ready", "label": "go"}]
        table = _build_edge_table(edges)
        assert "a" in table
        assert "b" in table

    def test_circuit_breaker_none(self):
        nodes = [{"id": "n1", "type": "agent"}]
        assert _build_circuit_breaker_section(nodes) is None

    def test_circuit_breaker_found(self):
        nodes = [{"id": "gate1", "type": "gate", "trip_condition": "x < 0.5", "fallback": "abort"}]
        result = _build_circuit_breaker_section(nodes)
        assert "gate1" in result
        assert "Circuit Breakers" in result
