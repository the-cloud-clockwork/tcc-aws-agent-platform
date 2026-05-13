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
    event_mode: str | None = None,
) -> ExecutionMode:
    """Read execution mode. Precedence: event_mode > EXECUTION_MODE env > SIMULATION.

    Args:
        aliases: Optional mapping of custom names to platform mode values.
                 Domain repos can pass their own vocabulary here.
        event_mode: Optional per-event override (e.g. from SFN payload).
                    When provided, takes precedence over the env var.

    If the resolved value is not a valid ExecutionMode, falls back to
    ``SIMULATION`` with a warning rather than crashing.
    """
    merged_aliases = {**_BUILTIN_ALIASES, **(aliases or {})}
    raw = event_mode or os.environ.get("EXECUTION_MODE", "simulation")
    raw = raw.strip().lower()
    raw = merged_aliases.get(raw, raw)

    try:
        return ExecutionMode(raw)
    except ValueError:
        logger.warning(
            "Unknown execution mode '%s' — falling back to simulation", raw
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
