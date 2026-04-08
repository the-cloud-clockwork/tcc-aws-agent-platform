"""MCP server observability — structured logging + OTEL spans for tool calls.

Provides ``MCPObservabilityHook`` which integrates with ``BaseMCPServer``
to emit structured JSON logs and OpenTelemetry spans for every tool
invocation. Domain-agnostic — works with any MCP server.

Usage::

    from agent_core.mcp.base_server import BaseMCPServer
    from agent_core.mcp.observability import MCPObservabilityHook

    hook = MCPObservabilityHook(server_id="market-data-mcp")
    mcp = BaseMCPServer("market-data-mcp", observability=hook)

Or via environment variable (auto-enabled when OTEL_ENABLED=true)::

    mcp = BaseMCPServer("market-data-mcp")
    # If OTEL_ENABLED=true, observability is auto-wired
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """Structured record for a single MCP tool invocation."""

    request_id: str
    server_id: str
    tool_name: str
    execution_mode: str
    start_time_ns: int
    end_time_ns: int = 0
    duration_ms: float = 0.0
    success: bool = True
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": "INFO" if self.success else "ERROR",
            "event": "mcp_tool_call",
            "request_id": self.request_id,
            "server_id": self.server_id,
            "tool_name": self.tool_name,
            "execution_mode": self.execution_mode,
            "duration_ms": round(self.duration_ms, 2),
            "success": self.success,
        }
        if not self.success:
            d["error_type"] = self.error_type
            d["error_message"] = self.error_message
        return d


class MCPObservabilityHook:
    """Observability hook for BaseMCPServer tool calls.

    Emits:
    - Structured JSON logs for every tool invocation (CloudWatch-queryable)
    - OpenTelemetry spans (when OTEL is configured via auto-instrumentation)

    Parameters
    ----------
    server_id:
        MCP server identifier (e.g. ``market-data-mcp``).
    execution_mode:
        Override execution mode. Auto-detected from ``EXECUTION_MODE`` env
        var if not provided.
    """

    def __init__(
        self,
        server_id: str,
        execution_mode: str | None = None,
    ) -> None:
        self.server_id = server_id
        self.execution_mode = execution_mode or os.getenv(
            "EXECUTION_MODE", "simulation"
        )
        self._structured_logger = logging.getLogger("agent_core.mcp.structured")
        self._tracer = _get_tracer(server_id)

    def on_tool_start(self, tool_name: str) -> ToolCallRecord:
        """Called before a tool handler executes. Returns a record to pass to on_tool_end."""
        record = ToolCallRecord(
            request_id=str(uuid.uuid4()),
            server_id=self.server_id,
            tool_name=tool_name,
            execution_mode=self.execution_mode,
            start_time_ns=time.perf_counter_ns(),
        )
        logger.debug("Tool call start: %s.%s", self.server_id, tool_name)
        return record

    def on_tool_end(self, record: ToolCallRecord, error: Exception | None = None) -> None:
        """Called after a tool handler completes (success or failure)."""
        record.end_time_ns = time.perf_counter_ns()
        record.duration_ms = (record.end_time_ns - record.start_time_ns) / 1_000_000

        if error is not None:
            record.success = False
            record.error_type = type(error).__name__
            record.error_message = str(error)

        # Emit structured JSON log
        import json

        self._structured_logger.info(json.dumps(record.to_dict(), default=str))

        # Emit OTEL span (if tracer is available)
        if self._tracer is not None:
            self._emit_span(record)

    def _emit_span(self, record: ToolCallRecord) -> None:
        """Create an OTEL span for the tool call."""
        try:
            from opentelemetry.trace import StatusCode

            with self._tracer.start_as_current_span(
                f"mcp.tool.{record.tool_name}",
                attributes={
                    "mcp.server_id": record.server_id,
                    "mcp.tool_name": record.tool_name,
                    "mcp.execution_mode": record.execution_mode,
                    "mcp.duration_ms": record.duration_ms,
                    "mcp.request_id": record.request_id,
                },
            ) as span:
                if not record.success:
                    span.set_status(StatusCode.ERROR, record.error_message or "")
                    span.set_attribute("error.type", record.error_type or "Unknown")
        except Exception:
            # OTEL not available — silently skip
            pass


def _get_tracer(server_id: str):
    """Get an OTEL tracer if opentelemetry is available, otherwise None."""
    try:
        from opentelemetry import trace

        return trace.get_tracer(f"agent_core.mcp.{server_id}", "1.0.0")
    except ImportError:
        return None


def auto_hook(server_id: str) -> MCPObservabilityHook | None:
    """Create an observability hook if OTEL or structured logging is enabled.

    Returns None if observability is disabled (default for local dev).
    Enabled when:
    - ``MCP_OBSERVABILITY=true`` env var is set, OR
    - ``OTEL_ENABLED=true`` env var is set
    """
    enabled = os.getenv("MCP_OBSERVABILITY", "").lower() == "true" or os.getenv(
        "OTEL_ENABLED", ""
    ).lower() == "true"

    if not enabled:
        return None

    return MCPObservabilityHook(server_id=server_id)
