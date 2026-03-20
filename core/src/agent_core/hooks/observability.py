"""ObservabilityHook -- structured logging for agent lifecycle events."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("agent_core.observability")


@dataclass
class ObservabilityHook:
    """Logs agent lifecycle events as structured JSON.

    Captures:
    - ``agent_start`` -- when the agent begins execution.
    - ``tool_end`` -- after each tool call (logs errors prominently).
    - ``agent_end`` -- when the agent finishes (includes elapsed time).

    Usage with Strands (callback-based)::

        hook = ObservabilityHook(agent_id="my_agent")
        agent = Agent(..., callbacks=[hook])

    This hook implements the Strands callback protocol by exposing
    ``on_agent_start``, ``on_tool_end``, and ``on_agent_end`` methods.
    """

    agent_id: str = "unknown"
    execution_mode: str = "simulation"
    _start_time: float = field(default=0.0, init=False, repr=False)
    _tool_calls: int = field(default=0, init=False, repr=False)
    _tool_errors: int = field(default=0, init=False, repr=False)

    # ---- Strands callback protocol ----

    def on_agent_start(self, **kwargs: Any) -> None:
        """Called when the agent starts execution."""
        self._start_time = time.monotonic()
        self._tool_calls = 0
        self._tool_errors = 0
        self._log(
            "agent_start",
            agent_id=self.agent_id,
            execution_mode=self.execution_mode,
        )

    def on_tool_end(
        self,
        tool_name: str = "unknown",
        error: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Called after each tool invocation completes."""
        self._tool_calls += 1
        payload: dict[str, Any] = {
            "agent_id": self.agent_id,
            "tool_name": tool_name,
        }
        if error:
            self._tool_errors += 1
            payload["error"] = error
            payload["level"] = "ERROR"
        self._log("tool_end", **payload)

    def on_agent_end(self, **kwargs: Any) -> None:
        """Called when the agent finishes execution."""
        elapsed = time.monotonic() - self._start_time if self._start_time else 0.0
        self._log(
            "agent_end",
            agent_id=self.agent_id,
            execution_mode=self.execution_mode,
            elapsed_seconds=round(elapsed, 3),
            tool_calls=self._tool_calls,
            tool_errors=self._tool_errors,
        )

    # ---- Internal ----

    @staticmethod
    def _log(event: str, **data: Any) -> None:
        record = {"event": event, **data}
        logger.info(json.dumps(record, default=str))
