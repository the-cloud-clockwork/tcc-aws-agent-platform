"""ExecutionMode enum and helpers."""
from __future__ import annotations

import os
from enum import StrEnum

from agent_core.schemas.execution_modes import ExecutionModes


class ExecutionMode(StrEnum):
    """The three execution modes supported by the platform."""

    SIMULATION = "simulation"
    STAGING = "staging"
    PRODUCTION = "production"


def get_execution_mode(
    *,
    aliases: dict[str, str] | None = None,
) -> ExecutionMode:
    """Read the current execution mode from the EXECUTION_MODE env var.

    Args:
        aliases: Optional mapping of custom names to platform mode values.
                 Domain repos can pass their own vocabulary here.

    Raises ValueError for unrecognised modes.
    """
    raw = os.environ.get("EXECUTION_MODE", "simulation").strip().lower()
    if aliases:
        raw = aliases.get(raw, raw)
    return ExecutionMode(raw)


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
