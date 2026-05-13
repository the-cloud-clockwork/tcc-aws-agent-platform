"""Tests for agent_core.execution.mode.get_execution_mode event_mode override."""
from __future__ import annotations

import os
from unittest.mock import patch


from agent_core.execution.mode import ExecutionMode, get_execution_mode


class TestGetExecutionMode:
    @patch.dict(os.environ, {"EXECUTION_MODE": "simulation"})
    def test_env_only_when_no_event_mode(self):
        assert get_execution_mode() == ExecutionMode.SIMULATION

    @patch.dict(os.environ, {"EXECUTION_MODE": "simulation"})
    def test_event_mode_overrides_env(self):
        assert get_execution_mode(event_mode="staging") == ExecutionMode.STAGING

    @patch.dict(os.environ, {"EXECUTION_MODE": "production"})
    def test_event_mode_none_falls_back_to_env(self):
        assert get_execution_mode(event_mode=None) == ExecutionMode.PRODUCTION

    @patch.dict(os.environ, {"EXECUTION_MODE": "simulation"})
    def test_alias_applied_to_event_mode(self):
        assert (
            get_execution_mode(event_mode="paper", aliases={"paper": "staging"})
            == ExecutionMode.STAGING
        )

    @patch.dict(os.environ, {"EXECUTION_MODE": "simulation"})
    def test_unknown_event_mode_falls_back_to_simulation(self):
        assert get_execution_mode(event_mode="nonsense") == ExecutionMode.SIMULATION
