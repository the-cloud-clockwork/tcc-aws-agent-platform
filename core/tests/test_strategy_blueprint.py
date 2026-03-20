"""Tests for StrategyBlueprint model."""
from __future__ import annotations

from agent_core.blueprints.strategy import StrategyBlueprint


class TestStrategyBlueprint:
    def test_parse_sample_yaml(self, sample_strategy_dict: dict) -> None:
        bp = StrategyBlueprint(**sample_strategy_dict)
        assert bp.id == "multi_signal_entry"
        assert bp.version == "1.0.0"
        assert bp.name == "Multi Signal Entry"

    def test_entry_conditions(self, sample_strategy_dict: dict) -> None:
        bp = StrategyBlueprint(**sample_strategy_dict)
        assert bp.entry_conditions.logic == "AND"
        assert len(bp.entry_conditions.conditions) == 2
        assert bp.entry_conditions.conditions[0].field == "score_a"
        assert bp.entry_conditions.conditions[0].op == "gte"
        assert bp.entry_conditions.conditions[0].value == 2.0

    def test_exit_conditions(self, sample_strategy_dict: dict) -> None:
        bp = StrategyBlueprint(**sample_strategy_dict)
        assert bp.exit_conditions.logic == "OR"
        assert len(bp.exit_conditions.conditions) == 2
        # First condition is a special type
        assert bp.exit_conditions.conditions[0].type == "threshold_breach"
        # Second is a field comparison
        assert bp.exit_conditions.conditions[1].field == "elapsed_time"

    def test_required_agents_and_mcps(self, sample_strategy_dict: dict) -> None:
        bp = StrategyBlueprint(**sample_strategy_dict)
        assert "detector" in bp.required_agents
        assert "data-mcp" in bp.required_mcps

    def test_asset_types_and_scopes(self, sample_strategy_dict: dict) -> None:
        bp = StrategyBlueprint(**sample_strategy_dict)
        assert bp.asset_types == ["default"]
        assert bp.scopes == ["global"]

    def test_concurrent_positions(self, sample_strategy_dict: dict) -> None:
        bp = StrategyBlueprint(**sample_strategy_dict)
        assert bp.max_concurrent_positions == 3
