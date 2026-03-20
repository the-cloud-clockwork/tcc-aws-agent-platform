"""ExecutionMode enum and helpers."""
from __future__ import annotations

import logging
import os
from enum import StrEnum

from agent_core.schemas.execution_modes import ExecutionModes

logger = logging.getLogger(__name__)

# Built-in aliases that map common domain vocabulary to platform modes.
# Domain repos (e.g. QITP) use "backtest", "paper", "live" but the
# platform canonical modes are "simulation", "staging", "production".
_BUILTIN_ALIASES: dict[str, str] = {
    "backtest": "simulation",
    "paper": "staging",
    "live": "production",
}


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
                 These are checked *after* built-in aliases.

    Built-in aliases (always active):
        backtest -> simulation, paper -> staging, live -> production.

    If the resolved value is not a valid ExecutionMode, falls back to
    ``SIMULATION`` with a warning rather than crashing. The platform
    must not crash on unknown modes.
    """
    raw = os.environ.get("EXECUTION_MODE", "simulation").strip().lower()

    # Apply built-in aliases first, then caller-supplied aliases.
    raw = _BUILTIN_ALIASES.get(raw, raw)
    if aliases:
        raw = aliases.get(raw, raw)

    try:
        return ExecutionMode(raw)
    except ValueError:
        logger.warning(
            "Unknown EXECUTION_MODE '%s' — falling back to simulation", raw
        )
        return ExecutionMode.SIMULATION


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
