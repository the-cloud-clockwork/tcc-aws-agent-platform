"""ConstraintHook -- enforces allocation-limit guardrails."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("agent_core.constraints")


@dataclass
class ConstraintHook:
    """Enforces maximum concurrent recommendations after agent invocation.

    If the agent produces more recommendations than ``max_recommendations``,
    the excess entries are truncated and a warning is logged.

    Usage with Strands (callback-based)::

        hook = ConstraintHook(max_recommendations=3)
        agent = Agent(..., callbacks=[hook])
    """

    max_recommendations: int = 3

    def on_agent_end(self, result: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any] | None:
        """Trim recommendations list if it exceeds the limit."""
        if result is None:
            return None

        recs = result.get("recommendations")
        if isinstance(recs, list) and len(recs) > self.max_recommendations:
            original_count = len(recs)
            result["recommendations"] = recs[: self.max_recommendations]
            logger.warning(
                "ConstraintHook: trimmed recommendations from %d to %d",
                original_count,
                self.max_recommendations,
            )
        return result
