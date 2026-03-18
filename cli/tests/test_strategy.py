"""Tests for agent_cli strategy sub-commands."""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from agent_cli.main import app

runner = CliRunner()


# Matches actual agent_core.blueprints.strategy.StrategyBlueprint schema
VALID_STRATEGY_YAML = """
id: test-strategy
name: Test Strategy
version: "1.0.0"
description: A test strategy
entry_conditions:
  logic: AND
  conditions:
    - type: gap_up
      field: gap_pct
      op: ">="
      value: 2.0
exit_conditions:
  logic: AND
  conditions:
    - type: stop_loss
      field: loss_pct
      op: "<="
      value: -1.5
position_sizing:
  method: risk_pct
  value: 0.02
"""

INVALID_STRATEGY_YAML = """
name: Missing Required Fields
description: No id or conditions
"""


class TestStrategyValidate:
    def test_validate_valid_strategy(self, tmp_path: Path):
        yaml_file = tmp_path / "strategy.yaml"
        yaml_file.write_text(VALID_STRATEGY_YAML)

        result = runner.invoke(app, ["strategy", "validate", str(yaml_file)])
        assert result.exit_code == 0
        assert "VALID" in result.output

    def test_validate_invalid_strategy(self, tmp_path: Path):
        yaml_file = tmp_path / "bad_strategy.yaml"
        yaml_file.write_text(INVALID_STRATEGY_YAML)

        result = runner.invoke(app, ["strategy", "validate", str(yaml_file)])
        assert result.exit_code == 1

    def test_validate_file_not_found(self):
        result = runner.invoke(app, ["strategy", "validate", "/nonexistent.yaml"])
        assert result.exit_code == 1


class TestStrategyList:
    def test_list_strategies(self, tmp_path: Path):
        (tmp_path / "s1.yaml").write_text(VALID_STRATEGY_YAML)
        (tmp_path / "s2.yaml").write_text(VALID_STRATEGY_YAML)

        result = runner.invoke(app, ["strategy", "list", "--dir", str(tmp_path)])
        assert result.exit_code == 0

    def test_list_empty_directory(self, tmp_path: Path):
        result = runner.invoke(app, ["strategy", "list", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "No strategy files" in result.output


class TestStrategyPromote:
    def test_promote_valid(self, tmp_path: Path):
        yaml_file = tmp_path / "strategy.yaml"
        yaml_file.write_text(VALID_STRATEGY_YAML)

        result = runner.invoke(app, ["strategy", "promote", str(yaml_file)])
        assert result.exit_code == 0
        assert "Promoted" in result.output

        # Verify status changed in file
        updated = yaml.safe_load(yaml_file.read_text())
        assert updated["status"] == "stable"
