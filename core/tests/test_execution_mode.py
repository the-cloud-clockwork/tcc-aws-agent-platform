"""Tests for ExecutionMode enum and helpers."""
from __future__ import annotations

import pytest

from agent_core.execution.mode import ExecutionMode, get_execution_mode, validate_agent_mode
from agent_core.schemas.execution_modes import ExecutionModes


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

    def test_aliases_parameter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        aliases = {"dev": "simulation", "qa": "staging", "prod": "production"}

        monkeypatch.setenv("EXECUTION_MODE", "dev")
        assert get_execution_mode(aliases=aliases) == ExecutionMode.SIMULATION

        monkeypatch.setenv("EXECUTION_MODE", "qa")
        assert get_execution_mode(aliases=aliases) == ExecutionMode.STAGING

        monkeypatch.setenv("EXECUTION_MODE", "prod")
        assert get_execution_mode(aliases=aliases) == ExecutionMode.PRODUCTION

    def test_aliases_unknown_still_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "unknown")
        with pytest.raises(ValueError):
            get_execution_mode(aliases={"dev": "simulation"})

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


class TestExecutionModesFieldAliases:
    def test_no_aliases_by_default(self) -> None:
        modes = ExecutionModes(simulation=True, staging=False)
        assert modes.simulation is True
        assert modes.staging is False

    def test_field_aliases_resolve(self) -> None:
        ExecutionModes.field_aliases = {"dev": "simulation", "qa": "staging"}
        try:
            modes = ExecutionModes(dev=True, qa=True)  # type: ignore[call-arg]
            assert modes.simulation is True
            assert modes.staging is True
        finally:
            ExecutionModes.field_aliases = {}

    def test_canonical_takes_precedence(self) -> None:
        ExecutionModes.field_aliases = {"dev": "simulation"}
        try:
            modes = ExecutionModes(simulation=False, dev=True)  # type: ignore[call-arg]
            assert modes.simulation is False  # canonical wins
        finally:
            ExecutionModes.field_aliases = {}
