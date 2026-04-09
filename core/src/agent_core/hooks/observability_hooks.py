"""Composite observability hook that wires Langfuse, audit log, cost tracking,
and structured logging into the Strands hook system.

This is the primary hook that agents should use. It composes:
- ``LangfuseHook`` for prompt tracking
- ``AuditLogWriter`` for compliance logging
- ``StructuredLogger`` for CloudWatch-friendly JSON logs
- ``CostTracker`` (via LangfuseHook) for token cost computation

Usage::

    from agent_core.hooks.observability_hooks import create_observability_hooks

    hook = create_observability_hooks(
        agent_id="my_agent",
        prompt_id="my_agent",
        prompt_version="v1.2",
        execution_mode="simulation",
    )
    agent = Agent(..., hooks=[hook])
"""
from __future__ import annotations

from collections.abc import Callable

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agent_core.observability.audit_log import AuditLogWriter
from agent_core.observability.langfuse_hook import LangfuseHook
from agent_core.observability.structured_logger import StructuredLogger

if TYPE_CHECKING:
    from strands.hooks import HookRegistry

logger = logging.getLogger("agent_core.hooks.observability")


@dataclass
class CompositeObservabilityHook:
    """Strands HookProvider that combines Langfuse, audit, and structured logging.

    Implements the Strands ``HookProvider`` protocol via ``register_hooks``.
    Also retains the legacy callback methods for backward compatibility and
    direct invocation in tests.

    Events handled:
    - ``BeforeInvocationEvent`` -- logs pipeline start, creates Langfuse trace
    - ``AfterModelCallEvent`` -- logs to Langfuse with cost
    - ``AfterToolCallEvent`` -- logs tool calls to structured logger
    - ``AfterInvocationEvent`` -- logs pipeline completion, finalizes trace, writes audit
    """

    agent_id: str = "unknown"
    prompt_id: str = "unknown"
    prompt_version: str = "unknown"
    execution_mode: str = "simulation"
    target: str = ""
    audit_table: str | None = None
    pii_filter: Callable[[str], str] | None = None

    _langfuse: LangfuseHook = field(init=False, repr=False)
    _audit: AuditLogWriter = field(init=False, repr=False)
    _logger: StructuredLogger = field(init=False, repr=False)
    _tool_calls: int = field(default=0, init=False, repr=False)
    _tool_errors: int = field(default=0, init=False, repr=False)
    _cycle_count: int = field(default=0, init=False, repr=False)
    _last_stop_reason: str = field(default="", init=False, repr=False)

    def __post_init__(self) -> None:
        self._langfuse = LangfuseHook(
            agent_id=self.agent_id,
            prompt_id=self.prompt_id,
            prompt_version=self.prompt_version,
            execution_mode=self.execution_mode,
            target=self.target,
            pii_filter=self.pii_filter,
        )
        self._audit = AuditLogWriter(table_name=self.audit_table)
        self._logger = StructuredLogger(
            agent_id=self.agent_id,
            execution_mode=self.execution_mode,
            prompt_version=self.prompt_version,
        )

    # ---- Strands HookProvider protocol ----

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register typed event callbacks with the Strands hook registry."""
        from strands.hooks.events import (
            AfterInvocationEvent,
            AfterModelCallEvent,
            AfterToolCallEvent,
            BeforeInvocationEvent,
        )

        registry.add_callback(BeforeInvocationEvent, self._on_before_invocation)
        registry.add_callback(AfterModelCallEvent, self._on_after_model_call)
        registry.add_callback(AfterToolCallEvent, self._on_after_tool_call)
        registry.add_callback(AfterInvocationEvent, self._on_after_invocation)

    # ---- Typed event handlers ----

    def _on_before_invocation(self, event: Any) -> None:
        """Handle BeforeInvocationEvent."""
        self.on_agent_start()

    def _on_after_model_call(self, event: Any) -> None:
        """Handle AfterModelCallEvent.

        Strands' ``AfterModelCallEvent`` carries ``stop_response`` (message +
        stop_reason) and ``exception`` but NOT token usage — usage is tracked
        on ``agent.event_loop_metrics.accumulated_usage`` and only finalised
        at the end of the invocation. We increment a cycle counter here and
        record the stop_reason so ``_on_after_invocation`` can emit a single
        aggregated generation span to Langfuse with the correct per-cycle
        count and the final stop reason.
        """
        self._cycle_count += 1
        stop_response = getattr(event, "stop_response", None)
        if stop_response is not None:
            self._last_stop_reason = str(getattr(stop_response, "stop_reason", "") or "")

    def _on_after_tool_call(self, event: Any) -> None:
        """Handle AfterToolCallEvent."""
        tool_name = "unknown"
        error = None
        # Extract tool name from the event's tool_use dict
        if hasattr(event, "tool_use") and event.tool_use:
            tool_name = event.tool_use.get("name", "unknown")
        # Check for exceptions
        if hasattr(event, "exception") and event.exception is not None:
            error = str(event.exception)
        self.on_tool_end(tool_name=tool_name, error=error)

    def _on_after_invocation(self, event: Any) -> None:
        """Handle AfterInvocationEvent.

        Reads the aggregated token usage and latency from the Strands
        ``event_loop_metrics`` on the agent, then synthesises ONE
        ``after_model_invocation`` call with the real data before finalising
        the trace. This is the only reliable place to read usage because
        Strands accumulates across cycles and only exposes the total here.
        """
        agent = getattr(event, "agent", None)
        if agent is not None:
            try:
                metrics = getattr(agent, "event_loop_metrics", None)
                if metrics is not None:
                    usage = getattr(metrics, "accumulated_usage", None) or {}
                    input_tokens = int(usage.get("inputTokens", 0) or 0)
                    output_tokens = int(usage.get("outputTokens", 0) or 0)
                    model_id = self._extract_model_id(agent)
                    self.after_model_invocation(
                        model_id=model_id,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        stop_reason=self._last_stop_reason,
                    )
            except Exception:
                logger.debug("Failed to extract usage from event_loop_metrics", exc_info=True)

        self.on_agent_end()

    @staticmethod
    def _extract_model_id(agent: Any) -> str:
        """Best-effort extraction of the underlying model id from a Strands agent."""
        try:
            model = getattr(agent, "model", None)
            if model is None:
                return "unknown"
            # LiteLLMModel / OpenAIModel / BedrockModel all store model_id in
            # their config dict under either ``model_id`` or ``modelId``.
            cfg = None
            if hasattr(model, "get_config"):
                cfg = model.get_config()
            elif hasattr(model, "config"):
                cfg = model.config
            if isinstance(cfg, dict):
                return str(cfg.get("model_id") or cfg.get("modelId") or "unknown")
        except Exception:
            pass
        return "unknown"

    # ---- Legacy callback methods (still used directly in tests) ----

    def on_agent_start(self, **kwargs: Any) -> None:
        """Called when the agent begins execution."""
        self._tool_calls = 0
        self._tool_errors = 0
        self._cycle_count = 0
        self._last_stop_reason = ""

        self._logger.info(
            "Agent starting",
            target=self.target,
        )
        self._langfuse.on_agent_start(**kwargs)

        try:
            self._audit.log(
                event_type="PIPELINE_STARTED",
                agent_id=self.agent_id,
                execution_mode=self.execution_mode,
                payload={
                    "target": self.target,
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
                    "tool_calls": self._tool_calls,
                    "tool_errors": self._tool_errors,
                    **summary,
                },
            )
        except Exception:
            logger.debug("Audit log write failed on agent end -- non-fatal")

    # ---- Callable protocol (backward compat for callbacks= usage) ----

    def __call__(self, **kwargs: Any) -> None:
        """Dispatch to the appropriate method based on event_type in kwargs.

        This enables backward compatibility with the old ``callbacks=[hook]``
        pattern where the hook was called as a function.
        """
        event_type = kwargs.pop("event_type", None)
        dispatch = {
            "agent_start": self.on_agent_start,
            "model_invocation": self.after_model_invocation,
            "tool_end": self.on_tool_end,
            "agent_end": self.on_agent_end,
        }
        handler = dispatch.get(event_type)
        if handler:
            handler(**kwargs)
        else:
            logger.debug("Unhandled event_type=%s in __call__", event_type)

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
    audit_table: str | None = None,
    pii_filter: Callable[[str], str] | None = None,
) -> CompositeObservabilityHook:
    """Factory function that creates an observability HookProvider.

    Returns a ``CompositeObservabilityHook`` instance suitable for
    ``Agent(..., hooks=[hook])``.

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
    audit_table:
        DynamoDB audit table name override.

    Returns
    -------
    A ``CompositeObservabilityHook`` instance (implements ``HookProvider``).
    """
    return CompositeObservabilityHook(
        agent_id=agent_id,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        execution_mode=execution_mode,
        target=target,
        audit_table=audit_table,
        pii_filter=pii_filter,
    )
