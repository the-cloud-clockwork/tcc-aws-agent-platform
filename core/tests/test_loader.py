"""Tests for BlueprintLoader."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from agent_core.blueprints.loader import BlueprintLoader, BlueprintLoadError

if TYPE_CHECKING:
    from pathlib import Path


class TestBlueprintLoader:
    def test_load_agent(self, tmp_blueprints: Path) -> None:
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_agent("gap_detector")
        assert bp.id == "gap_detector"
        assert bp.version == "1.2.0"

    def test_load_strategy(self, tmp_blueprints: Path) -> None:
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_strategy("gap_momentum_up")
        assert bp.id == "gap_momentum_up"

    def test_load_workflow(self, tmp_blueprints: Path) -> None:
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_workflow("weekly_gap_analysis")
        assert bp.id == "weekly_gap_analysis"
        assert len(bp.states) == 2
        assert bp.states[0].id == "ValidateSchedule"

    def test_load_agent_not_found(self, tmp_blueprints: Path) -> None:
        loader = BlueprintLoader(tmp_blueprints)
        with pytest.raises(BlueprintLoadError, match="not found"):
            loader.load_agent("nonexistent_agent")

    def test_load_agent_from_path(self, tmp_blueprints: Path) -> None:
        path = tmp_blueprints / "agents" / "gap_detector.yaml"
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_agent_from_path(path)
        assert bp.id == "gap_detector"

    def test_load_strategy_from_path(self, tmp_blueprints: Path) -> None:
        path = tmp_blueprints / "strategies" / "gap_momentum_up.yaml"
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_strategy_from_path(path)
        assert bp.id == "gap_momentum_up"
