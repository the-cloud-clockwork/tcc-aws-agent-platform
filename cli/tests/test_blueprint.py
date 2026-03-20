"""Tests for agent_cli blueprint sub-commands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from agent_cli.main import app

runner = CliRunner()

# Matches actual agent_core.blueprints.agent.AgentBlueprint schema
VALID_AGENT_YAML = """
id: test-agent
name: Test Agent
version: "1.0.0"
prompt_ref: test_agent_v1
model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
tools:
  - mcp: data-mcp
    tools:
      - get_data
"""

# Matches actual agent_core.blueprints.strategy.StrategyBlueprint schema
VALID_STRATEGY_YAML = """
id: test-strategy
name: Test Strategy
version: "1.0.0"
entry_conditions:
  logic: AND
  conditions:
    - type: threshold_up
exit_conditions:
  logic: AND
  conditions:
    - type: stop_loss
"""

EMPTY_YAML = ""


class TestBlueprintLint:
    def test_lint_valid_agent(self, tmp_path: Path):
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(VALID_AGENT_YAML)

        result = runner.invoke(app, ["blueprint", "lint", str(yaml_file)])
        assert result.exit_code == 0
        assert "PASS" in result.output

    def test_lint_valid_strategy(self, tmp_path: Path):
        yaml_file = tmp_path / "strategy.yaml"
        yaml_file.write_text(VALID_STRATEGY_YAML)

        result = runner.invoke(app, ["blueprint", "lint", str(yaml_file)])
        assert result.exit_code == 0

    def test_lint_file_not_found(self):
        result = runner.invoke(app, ["blueprint", "lint", "/nonexistent.yaml"])
        assert result.exit_code == 1

    def test_lint_empty_yaml(self, tmp_path: Path):
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text(EMPTY_YAML)

        result = runner.invoke(app, ["blueprint", "lint", str(yaml_file)])
        assert result.exit_code == 1
