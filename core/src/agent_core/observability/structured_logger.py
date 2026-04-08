"""Structured JSON logging for agents and services.

Every log line follows a fixed JSON schema so that
CloudWatch Logs Insights, Grafana, and Langfuse can query fields uniformly.

Usage::

    logger = StructuredLogger(
        agent_id="my_agent",
        execution_mode="simulation",
        prompt_version="my_agent_v1.2",
    )
    logger.info("Analysis started", target="ENTITY-1")
    logger.error("MCP timeout", tool="data-mcp", elapsed_ms=30000)
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid

from agent_core.runtime.middleware import get_correlation_id
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LogSchema:
    """Schema definition for a single structured log record.

    All logs conform to this shape. Extra fields are merged into
    the ``extra`` dict.
    """

    timestamp: str
    level: str
    message: str
    trace_id: str
    execution_id: str
    agent_id: str
    prompt_version: str
    execution_mode: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
            "trace_id": self.trace_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "prompt_version": self.prompt_version,
            "execution_mode": self.execution_mode,
        }
        if self.extra:
            d["extra"] = self.extra
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class StructuredLogger:
    """Emits structured JSON logs with standard fields.

    Parameters
    ----------
    agent_id:
        Identifier of the agent emitting the log.
    execution_mode:
        One of ``simulation``, ``staging``, ``production``.
    prompt_version:
        Prompt reference string (e.g. ``my_agent_v1.2``).
    trace_id:
        Distributed trace ID (X-Ray or custom). Auto-generated if not set.
    execution_id:
        Step Functions execution ID or pipeline run ID.
    logger_name:
        Python logger name. Defaults to ``agent_core.structured``.
    """

    def __init__(
        self,
        agent_id: str = "",
        execution_mode: str | None = None,
        prompt_version: str = "",
        trace_id: str | None = None,
        execution_id: str | None = None,
        logger_name: str = "agent_core.structured",
    ) -> None:
        self.agent_id = agent_id
        self.execution_mode = execution_mode or os.getenv(
            "EXECUTION_MODE", "simulation"
        )
        self.prompt_version = prompt_version
        self.trace_id = trace_id or os.getenv("_X_AMZN_TRACE_ID", str(uuid.uuid4()))
        self.execution_id = execution_id or os.getenv(
            "SFN_EXECUTION_ID", str(uuid.uuid4())
        )
        self._logger = logging.getLogger(logger_name)

    def _build_record(self, level: str, message: str, **extra: Any) -> LogSchema:
        return LogSchema(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            level=level,
            message=message,
            trace_id=get_correlation_id() or self.trace_id,
            execution_id=self.execution_id,
            agent_id=self.agent_id,
            prompt_version=self.prompt_version,
            execution_mode=self.execution_mode,
            extra=extra if extra else {},
        )

    def info(self, message: str, **extra: Any) -> LogSchema:
        record = self._build_record("INFO", message, **extra)
        self._logger.info(record.to_json())
        return record

    def warning(self, message: str, **extra: Any) -> LogSchema:
        record = self._build_record("WARNING", message, **extra)
        self._logger.warning(record.to_json())
        return record

    def error(self, message: str, **extra: Any) -> LogSchema:
        record = self._build_record("ERROR", message, **extra)
        self._logger.error(record.to_json())
        return record

    def debug(self, message: str, **extra: Any) -> LogSchema:
        record = self._build_record("DEBUG", message, **extra)
        self._logger.debug(record.to_json())
        return record

    def critical(self, message: str, **extra: Any) -> LogSchema:
        record = self._build_record("CRITICAL", message, **extra)
        self._logger.critical(record.to_json())
        return record
