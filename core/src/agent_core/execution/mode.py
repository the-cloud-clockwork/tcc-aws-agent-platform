"""ExecutionMode enum and helpers."""
from __future__ import annotations

import os
from enum import StrEnum

from agent_core.schemas.execution_modes import ExecutionModes

# Bidirectional mapping: domain aliases → platform enum values
DOMAIN_ALIASES: dict[str, str] = {
    "backtest": "simulation",
    "paper": "staging",
    "live": "production",
}

_REVERSE_ALIASES: dict[str, str] = {v: k for k, v in DOMAIN_ALIASES.items()}


class ExecutionMode(StrEnum):
    """The three execution modes supported by the platform."""

    SIMULATION = "simulation"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def domain_name(self) -> str:
        """Return the domain-friendly name (backtest/paper/live)."""
        return _REVERSE_ALIASES[self.value]


def get_execution_mode() -> ExecutionMode:
    """Read the current execution mode from the EXECUTION_MODE env var.

    Resolves domain aliases (backtest→simulation, paper→staging, live→production)
    before constructing the enum. Raises ValueError for invalid modes.
    """
    raw = os.environ.get("EXECUTION_MODE", "simulation").strip().lower()
    resolved = DOMAIN_ALIASES.get(raw, raw)
    return ExecutionMode(resolved)


def validate_agent_mode(
    execution_modes: ExecutionModes,
    mode: ExecutionMode | None = None,
) -> bool:
    """Return True if mode is enabled in the given execution-modes config.

    When mode is None the current environment mode is used.
    """
    if mode is None:
        mode = get_execution_mode()

    return bool(getattr(execution_modes, mode.value, False))
