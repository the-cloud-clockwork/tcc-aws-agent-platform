"""ExecutionMode enum and helpers."""
from __future__ import annotations

import logging
import os
from enum import StrEnum

from agent_core.schemas.execution_modes import ExecutionModes

logger = logging.getLogger(__name__)

# Default aliases — empty.  Domain repos register their own via the
# ``aliases`` parameter of ``get_execution_mode()`` or by calling
# ``register_aliases()`` at startup.
_BUILTIN_ALIASES: dict[str, str] = {}


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

    Built-in aliases are empty by default.  Domain repos can supply
    their own vocabulary via the ``aliases`` parameter or by populating
    ``_BUILTIN_ALIASES`` with ``register_aliases()`` at startup.

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
