"""Tests for ExecutionMode enum and helpers."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from agent_core.execution.mode import ExecutionMode, get_execution_mode, validate_agent_mode
from agent_core.schemas.execution_modes import ExecutionModes

if TYPE_CHECKING:
    pass


class TestExecutionMode:
    def test_default_is_simulation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EXECUTION_MODE", raising=False)
        assert get_execution_mode() == ExecutionMode.SIMULATION

    def test_all_modes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "staging")
        assert get_execution_mode() == ExecutionMode.STAGING

        monkeypatch.setenv("EXECUTION_MODE", "production")
        assert get_execution_mode() == ExecutionMode.PRODUCTION

        monkeypatch.setenv("EXECUTION_MODE", "simulation")
        assert get_execution_mode() == ExecutionMode.SIMULATION

    def test_invalid_mode_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "invalid_mode")
        with pytest.raises(ValueError):
            get_execution_mode()

    def test_domain_aliases(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "backtest")
        assert get_execution_mode() == ExecutionMode.SIMULATION

        monkeypatch.setenv("EXECUTION_MODE", "paper")
        assert get_execution_mode() == ExecutionMode.STAGING

        monkeypatch.setenv("EXECUTION_MODE", "live")
        assert get_execution_mode() == ExecutionMode.PRODUCTION

    def test_domain_name_property(self) -> None:
        assert ExecutionMode.SIMULATION.domain_name == "backtest"
        assert ExecutionMode.STAGING.domain_name == "paper"
        assert ExecutionMode.PRODUCTION.domain_name == "live"

    def test_validate_agent_mode_enabled(self) -> None:
        modes = ExecutionModes(simulation=True, staging=True, production=False)
        assert validate_agent_mode(modes, ExecutionMode.SIMULATION) is True
        assert validate_agent_mode(modes, ExecutionMode.STAGING) is True
        assert validate_agent_mode(modes, ExecutionMode.PRODUCTION) is False

    def test_validate_agent_mode_uses_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "staging")
        modes = ExecutionModes(simulation=True, staging=True, production=False)
        assert validate_agent_mode(modes) is True

    def test_validate_agent_mode_default_only_simulation(self) -> None:
        modes = ExecutionModes()  # simulation=True, staging=False, production=False
        assert validate_agent_mode(modes, ExecutionMode.SIMULATION) is True
        assert validate_agent_mode(modes, ExecutionMode.STAGING) is False
