"""Tests for ExecutionMode enum and helpers."""
from __future__ import annotations

from typing import TYPE_CHECKING

from agent_core.execution.mode import ExecutionMode, get_execution_mode, validate_agent_mode
from agent_core.schemas.execution_modes import ExecutionModes

if TYPE_CHECKING:
    import pytest


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

    def test_invalid_falls_back_to_simulation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "invalid_mode")
        assert get_execution_mode() == ExecutionMode.SIMULATION

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
