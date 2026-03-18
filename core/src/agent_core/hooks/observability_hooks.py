"""Composite observability hook that wires Langfuse, audit log, cost tracking,
and structured logging into the Strands hook system.

This is the primary hook that agents should use. It composes:
- ``LangfuseHook`` for prompt tracking
- ``AuditLogWriter`` for compliance logging
- ``StructuredLogger`` for CloudWatch-friendly JSON logs
- ``CostTracker`` (via LangfuseHook) for token cost computation

Usage::

    from agent_core.hooks.observability_hooks import create_observability_hooks

    hooks = create_observability_hooks(
        agent_id="gap_detector",
        prompt_id="gap_detector",
        prompt_version="v1.2",
        execution_mode="simulation",
    )
    agent = Agent(..., callbacks=hooks)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agent_core.observability.audit_log import AuditLogWriter
from agent_core.observability.langfuse_hook import LangfuseHook
from agent_core.observability.structured_logger import StructuredLogger

logger = logging.getLogger("agent_core.hooks.observability")


@dataclass
class CompositeObservabilityHook:
    """Strands callback hook that combines Langfuse, audit, and structured logging.

    Implements the Strands callback protocol:
    - ``on_agent_start`` -- logs pipeline start, creates Langfuse trace
    - ``after_model_invocation`` -- logs to Langfuse with cost
    - ``on_tool_end`` -- logs tool calls to structured logger
    - ``on_agent_end`` -- logs pipeline completion, finalizes trace, writes audit
    """

    agent_id: str = "unknown"
    prompt_id: str = "unknown"
    prompt_version: str = "unknown"
    execution_mode: str = "simulation"
    target: str = ""
    strategy_id: str = ""
    audit_table: str | None = None

    _langfuse: LangfuseHook = field(init=False, repr=False)
    _audit: AuditLogWriter = field(init=False, repr=False)
    _logger: StructuredLogger = field(init=False, repr=False)
    _tool_calls: int = field(default=0, init=False, repr=False)
    _tool_errors: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._langfuse = LangfuseHook(
            agent_id=self.agent_id,
            prompt_id=self.prompt_id,
            prompt_version=self.prompt_version,
            execution_mode=self.execution_mode,
            target=self.target,
            strategy_id=self.strategy_id,
        )
        self._audit = AuditLogWriter(table_name=self.audit_table)
        self._logger = StructuredLogger(
            agent_id=self.agent_id,
            execution_mode=self.execution_mode,
            prompt_version=self.prompt_version,
        )

    # ---- Strands callback protocol ----

    def on_agent_start(self, **kwargs: Any) -> None:
        """Called when the agent begins execution."""
        self._tool_calls = 0
        self._tool_errors = 0

        self._logger.info(
            "Agent starting",
            target=self.target,
            strategy_id=self.strategy_id,
        )
        self._langfuse.on_agent_start(**kwargs)

        try:
            self._audit.log(
                event_type="PIPELINE_STARTED",
                agent_id=self.agent_id,
                execution_mode=self.execution_mode,
                payload={
                    "target": self.target,
                    "strategy_id": self.strategy_id,
                    "prompt_version": self.prompt_version,
                },
            )
        except Exception:
            logger.debug("Audit log write failed on agent start -- non-fatal")

    def after_model_invocation(self, **kwargs: Any) -> None:
        """Called after each model invocation."""
        self._langfuse.after_model_invocation(**kwargs)

    def on_tool_end(
        self,
        tool_name: str = "unknown",
        error: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Called after each tool invocation."""
        self._tool_calls += 1
        if error:
            self._tool_errors += 1
            self._logger.error(
                "Tool call failed",
                tool_name=tool_name,
                error=error,
            )
        else:
            self._logger.debug(
                "Tool call completed",
                tool_name=tool_name,
            )

    def on_agent_end(self, **kwargs: Any) -> None:
        """Called when the agent finishes execution."""
        self._langfuse.on_agent_end(**kwargs)
        summary = self._langfuse.summary

        self._logger.info(
            "Agent completed",
            tool_calls=self._tool_calls,
            tool_errors=self._tool_errors,
            generations=summary["generation_count"],
            total_input_tokens=summary["total_input_tokens"],
            total_output_tokens=summary["total_output_tokens"],
            total_cost_usd=summary["total_cost_usd"],
        )

        try:
            self._audit.log(
                event_type="PIPELINE_COMPLETED",
                agent_id=self.agent_id,
                execution_mode=self.execution_mode,
                payload={
                    "target": self.target,
                    "strategy_id": self.strategy_id,
                    "tool_calls": self._tool_calls,
                    "tool_errors": self._tool_errors,
                    **summary,
                },
            )
        except Exception:
            logger.debug("Audit log write failed on agent end -- non-fatal")

    @property
    def langfuse_summary(self) -> dict[str, Any]:
        """Return token/cost summary from the Langfuse hook."""
        return self._langfuse.summary


def create_observability_hooks(
    agent_id: str = "unknown",
    prompt_id: str = "unknown",
    prompt_version: str = "unknown",
    execution_mode: str = "simulation",
    target: str = "",
    strategy_id: str = "",
    audit_table: str | None = None,
) -> list[Any]:
    """Factory function that creates the standard set of observability hooks.

    Returns a list of callback objects suitable for ``Agent(..., callbacks=hooks)``.

    Parameters
    ----------
    agent_id:
        Agent identifier.
    prompt_id:
        Prompt registry ID.
    prompt_version:
        Prompt version string.
    execution_mode:
        ``simulation``, ``staging``, or ``production``.
    target:
        Target entity (optional).
    strategy_id:
        Strategy identifier (optional).
    audit_table:
        DynamoDB audit table name override.

    Returns
    -------
    List containing a ``CompositeObservabilityHook`` instance.
    """
    hook = CompositeObservabilityHook(
        agent_id=agent_id,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        execution_mode=execution_mode,
        target=target,
        strategy_id=strategy_id,
        audit_table=audit_table,
    )
    return [hook]
