# P18 -- Observability

> **Self-contained plan.** A fresh Claude Code agent reads ONLY this file and can execute everything.

## Metadata

| Field | Value |
|---|---|
| Plan ID | P18 |
| Plane Tickets | ROOT-62 |
| Target Repos | `~/dev/tccw-agent-core` (hooks + observability modules), `~/dev/tccw-agent-infra` (observability CDK stack) |
| Depends On | P02 (hooks framework), P11 (observability stack skeleton) |
| Batch | 4 (Phase 2) |

## Objective

Build the full QITP observability stack:

- **Langfuse Integration** -- AfterModelInvocationEvent hook that logs prompt/completion to Langfuse with agent_id, prompt_version, execution_mode, token cost
- **X-Ray Distributed Tracing** -- helpers for custom segments/subsegments across EventBridge -> SFN -> Lambda -> AgentCore -> MCP
- **Structured JSON Logging** -- schema-validated structured logger with trace_id, execution_id, agent_id, prompt_version
- **DynamoDB Audit Log** -- 15 event types, 5-year MiFID II retention, idempotent writes
- **Cost Tracker** -- token cost computation per model using Bedrock pricing table
- **Telegram Alerts** -- SNS topic -> Lambda -> Telegram bot for circuit breakers, failures, weekly P&L
- **CloudWatch Dashboards (CDK)** -- 8 widgets: pipeline executions, agent latency, token cost, portfolio NAV, open positions, risk PASS/FAIL, 2FA approval rate, IBKR health
- **Observability Hooks** -- wire Langfuse + audit + cost tracking into Strands hook system

---

## Target Repo Structure

### Additions to `tccw-agent-core`

```
tccw-agent-core/
├── src/
│   └── agent_core/
│       ├── observability/
│       │   ├── __init__.py
│       │   ├── langfuse_hook.py       # AfterModelInvocationEvent -> Langfuse
│       │   ├── xray_tracing.py        # X-Ray segment/subsegment helpers
│       │   ├── structured_logger.py   # JSON structured logging
│       │   ├── audit_log.py           # DynamoDB audit log writer (15 event types)
│       │   ├── cost_tracker.py        # Token cost computation per model
│       │   └── alerts.py              # SNS publish for Telegram alerts
│       └── hooks/
│           └── observability_hooks.py # Wire Langfuse + audit into Strands hook system
├── tests/
│   ├── test_langfuse_hook.py
│   ├── test_xray_tracing.py
│   ├── test_structured_logger.py
│   ├── test_audit_log.py
│   ├── test_cost_tracker.py
│   ├── test_alerts.py
│   └── test_observability_hooks.py
```

### Additions to `tccw-agent-infra`

```
tccw-agent-infra/
├── stacks/
│   └── observability_stack.py         # REPLACE: full CloudWatch dashboards, X-Ray, SNS, log groups
├── lambda/
│   └── telegram_alert/
│       └── handler.py                 # SNS -> Telegram bot Lambda
├── tests/
│   └── test_observability_stack.py    # CDK assertion tests
```

---

## Full Inline Code

---

### `src/agent_core/observability/__init__.py`

```python
"""QITP Observability subsystem.

Provides Langfuse integration, X-Ray tracing, structured logging,
DynamoDB audit logging, cost tracking, and SNS alerting.
"""
from __future__ import annotations

from agent_core.observability.audit_log import AuditEventType, AuditLogWriter
from agent_core.observability.cost_tracker import CostTracker
from agent_core.observability.langfuse_hook import LangfuseHook
from agent_core.observability.structured_logger import StructuredLogger, LogSchema
from agent_core.observability.xray_tracing import XRayTracer
from agent_core.observability.alerts import AlertPublisher

__all__ = [
    "AuditEventType",
    "AuditLogWriter",
    "AlertPublisher",
    "CostTracker",
    "LangfuseHook",
    "LogSchema",
    "StructuredLogger",
    "XRayTracer",
]
```

---

### `src/agent_core/observability/structured_logger.py`

```python
"""Structured JSON logging for QITP agents and services.

Every log line emitted by QITP components follows a fixed JSON schema so that
CloudWatch Logs Insights, Grafana, and Langfuse can query fields uniformly.

Usage::

    logger = StructuredLogger(
        agent_id="gap_detector",
        execution_mode="backtest",
        prompt_version="gap_detector_v1.2",
    )
    logger.info("Gap analysis started", symbol="AAPL", gap_pct=2.3)
    logger.error("MCP timeout", tool="market-data-mcp", elapsed_ms=30000)
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LogSchema:
    """Schema definition for a single structured log record.

    All QITP logs conform to this shape. Extra fields are merged into
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
    """Emits structured JSON logs with QITP-standard fields.

    Parameters
    ----------
    agent_id:
        Identifier of the agent emitting the log.
    execution_mode:
        One of ``backtest``, ``paper``, ``live``.
    prompt_version:
        Prompt reference string (e.g. ``gap_detector_v1.2``).
    trace_id:
        Distributed trace ID (X-Ray or custom). Auto-generated if not set.
    execution_id:
        Step Functions execution ID or pipeline run ID.
    logger_name:
        Python logger name. Defaults to ``qitp.structured``.
    """

    def __init__(
        self,
        agent_id: str = "unknown",
        execution_mode: str | None = None,
        prompt_version: str = "unknown",
        trace_id: str | None = None,
        execution_id: str | None = None,
        logger_name: str = "qitp.structured",
    ) -> None:
        self.agent_id = agent_id
        self.execution_mode = execution_mode or os.getenv("EXECUTION_MODE", "backtest")
        self.prompt_version = prompt_version
        self.trace_id = trace_id or os.getenv("_X_AMZN_TRACE_ID", str(uuid.uuid4()))
        self.execution_id = execution_id or os.getenv("SFN_EXECUTION_ID", str(uuid.uuid4()))
        self._logger = logging.getLogger(logger_name)

    def _build_record(self, level: str, message: str, **extra: Any) -> LogSchema:
        return LogSchema(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            level=level,
            message=message,
            trace_id=self.trace_id,
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
```

---

### `src/agent_core/observability/cost_tracker.py`

```python
"""Token cost computation per model using Bedrock pricing.

Maintains a lookup table of per-token costs for Bedrock models and
computes the cost of a single model invocation given input/output token counts.

Usage::

    tracker = CostTracker()
    cost = tracker.compute_cost(
        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        input_tokens=1500,
        output_tokens=800,
    )
    # cost.total_usd == 0.0069  (example)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenCost:
    """Result of a cost computation."""

    model_id: str
    input_tokens: int
    output_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_usd: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "input_cost_usd": round(self.input_cost_usd, 8),
            "output_cost_usd": round(self.output_cost_usd, 8),
            "total_usd": round(self.total_usd, 8),
        }


# Pricing per 1K tokens in USD (as of 2025-05)
# Source: https://aws.amazon.com/bedrock/pricing/
_PRICING: dict[str, tuple[float, float]] = {
    # (input_per_1k, output_per_1k)
    # Claude 4 Sonnet
    "us.anthropic.claude-sonnet-4-20250514-v1:0": (0.003, 0.015),
    "eu.anthropic.claude-sonnet-4-6": (0.003, 0.015),
    "anthropic.claude-sonnet-4-20250514-v1:0": (0.003, 0.015),
    # Claude 4 Opus
    "eu.anthropic.claude-opus-4-6-v1": (0.015, 0.075),
    "us.anthropic.claude-opus-4-20250514-v1:0": (0.015, 0.075),
    "anthropic.claude-opus-4-20250514-v1:0": (0.015, 0.075),
    # Claude 3.5 Sonnet (v2)
    "anthropic.claude-3-5-sonnet-20241022-v2:0": (0.003, 0.015),
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0": (0.003, 0.015),
    # Claude 3.5 Haiku
    "anthropic.claude-3-5-haiku-20241022-v1:0": (0.0008, 0.004),
    "us.anthropic.claude-3-5-haiku-20241022-v1:0": (0.0008, 0.004),
    # Nova Micro
    "amazon.nova-micro-v1:0": (0.000035, 0.00014),
    # Nova Lite
    "amazon.nova-lite-v1:0": (0.00006, 0.00024),
    # Nova Pro
    "amazon.nova-pro-v1:0": (0.0008, 0.0032),
}

# Fallback for unknown models
_DEFAULT_PRICING: tuple[float, float] = (0.003, 0.015)


class CostTracker:
    """Computes token costs for Bedrock model invocations.

    Parameters
    ----------
    custom_pricing:
        Optional dict to override or extend the built-in pricing table.
        Keys are model IDs, values are ``(input_per_1k, output_per_1k)`` tuples.
    """

    def __init__(self, custom_pricing: dict[str, tuple[float, float]] | None = None) -> None:
        self._pricing = dict(_PRICING)
        if custom_pricing:
            self._pricing.update(custom_pricing)

    def get_pricing(self, model_id: str) -> tuple[float, float]:
        """Return ``(input_per_1k, output_per_1k)`` for a model ID.

        Falls back to default pricing if the model is unknown.
        """
        return self._pricing.get(model_id, _DEFAULT_PRICING)

    def compute_cost(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> TokenCost:
        """Compute the USD cost of a single model invocation.

        Parameters
        ----------
        model_id:
            Bedrock model identifier.
        input_tokens:
            Number of input tokens.
        output_tokens:
            Number of output tokens.

        Returns
        -------
        TokenCost:
            Breakdown of costs.
        """
        input_per_1k, output_per_1k = self.get_pricing(model_id)
        input_cost = (input_tokens / 1000.0) * input_per_1k
        output_cost = (output_tokens / 1000.0) * output_per_1k

        return TokenCost(
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            total_usd=input_cost + output_cost,
        )

    @property
    def known_models(self) -> list[str]:
        """Return list of all model IDs with known pricing."""
        return sorted(self._pricing.keys())
```

---

### `src/agent_core/observability/langfuse_hook.py`

```python
"""Langfuse integration hook for Strands agents.

Logs every model invocation to Langfuse with structured tags: agent_id,
prompt_id, prompt_version, execution_mode, symbol, strategy_id.
Also computes token cost via CostTracker.

Usage::

    hook = LangfuseHook(
        agent_id="gap_detector",
        prompt_id="gap_detector",
        prompt_version="v1.2",
        execution_mode="backtest",
    )
    agent = Agent(..., callbacks=[hook])

Environment variables:
- ``LANGFUSE_PUBLIC_KEY`` -- Langfuse public key
- ``LANGFUSE_SECRET_KEY`` -- Langfuse secret key (via env var only, never hardcoded)
- ``LANGFUSE_HOST`` -- Langfuse host URL (default: https://cloud.langfuse.com)
- ``LANGFUSE_ENABLED`` -- set to ``false`` to disable (default: ``true``)
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent_core.observability.cost_tracker import CostTracker

logger = logging.getLogger("qitp.langfuse")

# Lazy-loaded Langfuse client
_langfuse_client: Any = None


def _get_langfuse_client() -> Any:
    """Lazily initialize the Langfuse client.

    Returns None if langfuse is not installed or not configured.
    """
    global _langfuse_client  # noqa: PLW0603

    if _langfuse_client is not None:
        return _langfuse_client

    enabled = os.getenv("LANGFUSE_ENABLED", "true").lower()
    if enabled == "false":
        logger.info("Langfuse disabled via LANGFUSE_ENABLED=false")
        return None

    try:
        from langfuse import Langfuse  # type: ignore[import-untyped]

        _langfuse_client = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
        logger.info("Langfuse client initialized")
        return _langfuse_client
    except ImportError:
        logger.warning("langfuse package not installed -- tracing disabled")
        return None
    except Exception:
        logger.exception("Failed to initialize Langfuse client")
        return None


def reset_langfuse_client() -> None:
    """Reset the cached Langfuse client. Used in tests."""
    global _langfuse_client  # noqa: PLW0603
    _langfuse_client = None


@dataclass
class LangfuseHook:
    """Strands callback hook that logs model invocations to Langfuse.

    Implements the Strands callback protocol:
    - ``on_agent_start`` -- creates a Langfuse trace
    - ``after_model_invocation`` -- logs generation with token counts + cost
    - ``on_agent_end`` -- finalizes the trace

    Attributes
    ----------
    agent_id:
        Agent identifier for tagging.
    prompt_id:
        Prompt registry ID (without version).
    prompt_version:
        Prompt version string.
    execution_mode:
        One of ``backtest``, ``paper``, ``live``.
    symbol:
        Trading symbol being processed (optional).
    strategy_id:
        Strategy identifier (optional).
    """

    agent_id: str = "unknown"
    prompt_id: str = "unknown"
    prompt_version: str = "unknown"
    execution_mode: str = "backtest"
    symbol: str = ""
    strategy_id: str = ""

    _trace: Any = field(default=None, init=False, repr=False)
    _generation_count: int = field(default=0, init=False, repr=False)
    _total_input_tokens: int = field(default=0, init=False, repr=False)
    _total_output_tokens: int = field(default=0, init=False, repr=False)
    _total_cost_usd: float = field(default=0.0, init=False, repr=False)
    _start_time: float = field(default=0.0, init=False, repr=False)
    _cost_tracker: CostTracker = field(default_factory=CostTracker, init=False, repr=False)
    _trace_id: str = field(default="", init=False, repr=False)

    def _tags(self) -> dict[str, str]:
        tags: dict[str, str] = {
            "agent_id": self.agent_id,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "execution_mode": self.execution_mode,
        }
        if self.symbol:
            tags["symbol"] = self.symbol
        if self.strategy_id:
            tags["strategy_id"] = self.strategy_id
        return tags

    # ---- Strands callback protocol ----

    def on_agent_start(self, **kwargs: Any) -> None:
        """Create a Langfuse trace for this agent invocation."""
        self._start_time = time.monotonic()
        self._generation_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost_usd = 0.0
        self._trace_id = str(uuid.uuid4())

        client = _get_langfuse_client()
        if client is None:
            return

        try:
            self._trace = client.trace(
                id=self._trace_id,
                name=f"agent:{self.agent_id}",
                metadata=self._tags(),
                tags=list(self._tags().values()),
            )
            logger.debug("Langfuse trace created: %s", self._trace_id)
        except Exception:
            logger.exception("Failed to create Langfuse trace")
            self._trace = None

    def after_model_invocation(
        self,
        model_id: str = "unknown",
        input_tokens: int = 0,
        output_tokens: int = 0,
        stop_reason: str = "",
        **kwargs: Any,
    ) -> None:
        """Log a model generation to the current Langfuse trace.

        Parameters
        ----------
        model_id:
            Bedrock model identifier.
        input_tokens:
            Number of input tokens consumed.
        output_tokens:
            Number of output tokens generated.
        stop_reason:
            Model stop reason (e.g. ``end_turn``, ``tool_use``).
        """
        self._generation_count += 1
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

        cost = self._cost_tracker.compute_cost(model_id, input_tokens, output_tokens)
        self._total_cost_usd += cost.total_usd

        logger.info(
            "Model invocation #%d: model=%s input=%d output=%d cost=$%.6f",
            self._generation_count,
            model_id,
            input_tokens,
            output_tokens,
            cost.total_usd,
        )

        if self._trace is None:
            return

        try:
            self._trace.generation(
                name=f"generation-{self._generation_count}",
                model=model_id,
                model_parameters={"stop_reason": stop_reason},
                usage={
                    "input": input_tokens,
                    "output": output_tokens,
                    "total": input_tokens + output_tokens,
                    "unit": "TOKENS",
                },
                metadata={
                    **self._tags(),
                    "cost_usd": cost.total_usd,
                    "generation_number": self._generation_count,
                },
            )
        except Exception:
            logger.exception("Failed to log Langfuse generation")

    def on_agent_end(self, **kwargs: Any) -> None:
        """Finalize the Langfuse trace with summary metadata."""
        elapsed = time.monotonic() - self._start_time if self._start_time else 0.0

        logger.info(
            "Agent %s completed: generations=%d input_tokens=%d output_tokens=%d "
            "total_cost=$%.6f elapsed=%.3fs",
            self.agent_id,
            self._generation_count,
            self._total_input_tokens,
            self._total_output_tokens,
            self._total_cost_usd,
            elapsed,
        )

        if self._trace is None:
            return

        try:
            self._trace.update(
                metadata={
                    **self._tags(),
                    "total_generations": self._generation_count,
                    "total_input_tokens": self._total_input_tokens,
                    "total_output_tokens": self._total_output_tokens,
                    "total_cost_usd": self._total_cost_usd,
                    "elapsed_seconds": round(elapsed, 3),
                },
            )
        except Exception:
            logger.exception("Failed to update Langfuse trace")

        # Flush to ensure data is sent
        try:
            client = _get_langfuse_client()
            if client:
                client.flush()
        except Exception:
            logger.exception("Failed to flush Langfuse client")

    @property
    def summary(self) -> dict[str, Any]:
        """Return a summary dict of this hook's tracked metrics."""
        return {
            "agent_id": self.agent_id,
            "trace_id": self._trace_id,
            "generation_count": self._generation_count,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_cost_usd": round(self._total_cost_usd, 8),
        }
```

---

### `src/agent_core/observability/xray_tracing.py`

```python
"""X-Ray distributed tracing helpers for QITP.

Provides a thin wrapper around ``aws_xray_sdk`` to create custom segments
and subsegments for agent reasoning steps, MCP calls, and pipeline stages.

Usage::

    tracer = XRayTracer(service_name="gap_detector")

    with tracer.subsegment("fetch_ohlcv", symbol="AAPL") as sub:
        data = mcp_client.call("get_ohlcv", symbol="AAPL")
        sub.put_annotation("rows", len(data))

    # Or as a decorator
    @tracer.capture("compute_gap")
    def compute_gap(open_price, close_price):
        return (open_price - close_price) / close_price

Environment variables:
- ``AWS_XRAY_DAEMON_ADDRESS`` -- X-Ray daemon address (set by Lambda runtime)
- ``AWS_XRAY_SDK_ENABLED`` -- set to ``false`` to disable (default: ``true``)
- ``_X_AMZN_TRACE_ID`` -- trace ID injected by Lambda/API Gateway
"""
from __future__ import annotations

import functools
import logging
import os
from contextlib import contextmanager
from typing import Any, Callable, Generator

logger = logging.getLogger("qitp.xray")

# Lazy-loaded X-Ray recorder
_recorder: Any = None


def _get_recorder() -> Any:
    """Lazily initialize the X-Ray recorder.

    Returns None if aws-xray-sdk is not installed or disabled.
    """
    global _recorder  # noqa: PLW0603

    if _recorder is not None:
        return _recorder

    enabled = os.getenv("AWS_XRAY_SDK_ENABLED", "true").lower()
    if enabled == "false":
        logger.info("X-Ray SDK disabled via AWS_XRAY_SDK_ENABLED=false")
        return None

    try:
        from aws_xray_sdk.core import xray_recorder  # type: ignore[import-untyped]

        _recorder = xray_recorder
        logger.info("X-Ray recorder initialized")
        return _recorder
    except ImportError:
        logger.warning("aws-xray-sdk not installed -- X-Ray tracing disabled")
        return None


def reset_recorder() -> None:
    """Reset the cached recorder. Used in tests."""
    global _recorder  # noqa: PLW0603
    _recorder = None


class _NoOpSubsegment:
    """Dummy subsegment when X-Ray is disabled."""

    def put_annotation(self, key: str, value: Any) -> None:
        pass

    def put_metadata(self, key: str, value: Any, namespace: str = "default") -> None:
        pass

    def add_exception(self, exception: Exception, stack: Any = None) -> None:
        pass

    def __enter__(self) -> "_NoOpSubsegment":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class XRayTracer:
    """Wrapper around aws_xray_sdk for QITP-specific tracing.

    Parameters
    ----------
    service_name:
        Name of the service for annotations (e.g. ``gap_detector``).
    """

    def __init__(self, service_name: str = "qitp") -> None:
        self.service_name = service_name

    @contextmanager
    def subsegment(self, name: str, **annotations: Any) -> Generator[Any, None, None]:
        """Create a named X-Ray subsegment with optional annotations.

        Parameters
        ----------
        name:
            Subsegment name (e.g. ``fetch_ohlcv``, ``compute_sentiment``).
        **annotations:
            Key-value pairs added as X-Ray annotations (indexed, searchable).

        Yields
        ------
        The subsegment object (or a no-op if X-Ray is disabled).
        """
        recorder = _get_recorder()

        if recorder is None:
            yield _NoOpSubsegment()
            return

        try:
            subseg = recorder.begin_subsegment(name)
            if subseg is None:
                yield _NoOpSubsegment()
                return

            subseg.put_annotation("service", self.service_name)
            for key, value in annotations.items():
                subseg.put_annotation(key, value)

            try:
                yield subseg
            except Exception as exc:
                subseg.add_exception(exc, exc.__traceback__)
                raise
            finally:
                recorder.end_subsegment()
        except Exception:
            logger.debug("X-Ray subsegment creation failed -- falling back to no-op")
            yield _NoOpSubsegment()

    def capture(self, name: str, **annotations: Any) -> Callable:
        """Decorator that wraps a function in an X-Ray subsegment.

        Parameters
        ----------
        name:
            Subsegment name.
        **annotations:
            Static annotations to attach.

        Returns
        -------
        Decorated function.
        """

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with self.subsegment(name, **annotations):
                    return func(*args, **kwargs)

            return wrapper

        return decorator

    def add_annotation(self, key: str, value: Any) -> None:
        """Add an annotation to the current segment/subsegment."""
        recorder = _get_recorder()
        if recorder is None:
            return
        try:
            segment = recorder.current_subsegment() or recorder.current_segment()
            if segment:
                segment.put_annotation(key, value)
        except Exception:
            logger.debug("Failed to add X-Ray annotation: %s=%s", key, value)

    def add_metadata(self, key: str, value: Any, namespace: str = "qitp") -> None:
        """Add metadata to the current segment/subsegment."""
        recorder = _get_recorder()
        if recorder is None:
            return
        try:
            segment = recorder.current_subsegment() or recorder.current_segment()
            if segment:
                segment.put_metadata(key, value, namespace)
        except Exception:
            logger.debug("Failed to add X-Ray metadata: %s", key)
```

---

### `src/agent_core/observability/audit_log.py`

```python
"""DynamoDB audit log writer for QITP.

Implements MiFID II compliant audit logging with 15 event types and
5-year retention. Every financial decision is logged with timestamp (ms),
agent_id, execution_mode, and event-specific payload.

Usage::

    writer = AuditLogWriter(table_name="qitp_dev_audit_log")
    writer.log(
        event_type=AuditEventType.ORDER_REQUESTED,
        agent_id="execution_agent",
        execution_mode="live",
        payload={
            "symbol": "AAPL",
            "isin": "US0378331005",
            "side": "BUY",
            "qty": 10,
            "price": 185.50,
            "venue": "SMART",
            "rationale": "Gap momentum up signal confirmed",
        },
    )

Environment variables:
- ``QITP_AUDIT_TABLE`` -- DynamoDB table name override
- ``EXECUTION_MODE`` -- default execution mode if not provided per call
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from enum import Enum
from typing import Any

logger = logging.getLogger("qitp.audit")

# 5-year retention in seconds (MiFID II)
MIFID_II_RETENTION_SECONDS = 157_680_000  # ~5 years


class AuditEventType(str, Enum):
    """All 15 QITP audit event types."""

    ORDER_REQUESTED = "ORDER_REQUESTED"
    ORDER_APPROVED = "ORDER_APPROVED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_FILLED = "ORDER_FILLED"
    RISK_CHECK_PASS = "RISK_CHECK_PASS"
    RISK_CHECK_FAIL = "RISK_CHECK_FAIL"
    CIRCUIT_BREAKER_TRIPPED = "CIRCUIT_BREAKER_TRIPPED"
    CIRCUIT_BREAKER_RESET = "CIRCUIT_BREAKER_RESET"
    PIPELINE_STARTED = "PIPELINE_STARTED"
    PIPELINE_COMPLETED = "PIPELINE_COMPLETED"
    PIPELINE_FAILED = "PIPELINE_FAILED"
    PROMPT_LOADED = "PROMPT_LOADED"
    STRATEGY_EVALUATED = "STRATEGY_EVALUATED"
    POSITION_CLOSED = "POSITION_CLOSED"


# Event types that require full MiFID II fields
_FINANCIAL_EVENTS = {
    AuditEventType.ORDER_REQUESTED,
    AuditEventType.ORDER_APPROVED,
    AuditEventType.ORDER_SUBMITTED,
    AuditEventType.ORDER_FILLED,
    AuditEventType.POSITION_CLOSED,
}

# Required fields for financial events
_FINANCIAL_REQUIRED_FIELDS = {"symbol"}


class AuditLogError(Exception):
    """Raised when an audit log write fails."""


class AuditLogWriter:
    """Writes audit events to DynamoDB with idempotency and TTL.

    Parameters
    ----------
    table_name:
        DynamoDB table name. Defaults to ``QITP_AUDIT_TABLE`` env var.
    dynamodb_client:
        Optional boto3 DynamoDB client (injected for testing).
    retention_seconds:
        TTL duration in seconds. Default: 5 years (MiFID II).
    """

    def __init__(
        self,
        table_name: str | None = None,
        dynamodb_client: Any = None,
        retention_seconds: int = MIFID_II_RETENTION_SECONDS,
    ) -> None:
        self.table_name = table_name or os.getenv("QITP_AUDIT_TABLE", "qitp_audit_log")
        self._client = dynamodb_client
        self._retention_seconds = retention_seconds

    def _get_client(self) -> Any:
        """Lazily initialize the DynamoDB client."""
        if self._client is None:
            import boto3  # type: ignore[import-untyped]

            self._client = boto3.resource("dynamodb").Table(self.table_name)
        return self._client

    def _validate_financial_event(self, event_type: AuditEventType, payload: dict[str, Any]) -> None:
        """Validate that financial events contain required fields."""
        if event_type in _FINANCIAL_EVENTS:
            missing = _FINANCIAL_REQUIRED_FIELDS - set(payload.keys())
            if missing:
                raise AuditLogError(
                    f"Financial event {event_type.value} missing required fields: {missing}"
                )

    def log(
        self,
        event_type: AuditEventType,
        agent_id: str = "unknown",
        execution_mode: str | None = None,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        execution_id: str | None = None,
    ) -> dict[str, Any]:
        """Write an audit event to DynamoDB.

        Parameters
        ----------
        event_type:
            One of the 15 ``AuditEventType`` values.
        agent_id:
            Agent that generated the event.
        execution_mode:
            ``backtest``, ``paper``, or ``live``.
        payload:
            Event-specific data dict.
        idempotency_key:
            Unique key for deduplication. Auto-generated if not provided.
        execution_id:
            Pipeline/SFN execution ID for correlation.

        Returns
        -------
        The complete item dict that was written.
        """
        mode = execution_mode or os.getenv("EXECUTION_MODE", "backtest")
        payload = payload or {}

        self._validate_financial_event(event_type, payload)

        now_ms = int(time.time() * 1000)
        event_id = idempotency_key or str(uuid.uuid4())
        ttl = int(time.time()) + self._retention_seconds

        item: dict[str, Any] = {
            "event_id": event_id,
            "event_type": event_type.value,
            "timestamp_ms": now_ms,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now_ms / 1000)),
            "agent_id": agent_id,
            "execution_mode": mode,
            "execution_id": execution_id or os.getenv("SFN_EXECUTION_ID", "unknown"),
            "payload": payload,
            "ttl": ttl,
        }

        logger.info(
            "Audit event: type=%s agent=%s mode=%s event_id=%s",
            event_type.value,
            agent_id,
            mode,
            event_id,
        )

        try:
            table = self._get_client()
            # Condition expression ensures idempotency -- no overwrite if event_id exists
            table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(event_id)",
            )
        except Exception as exc:
            # ClientError for ConditionalCheckFailedException means duplicate -- that's OK
            exc_name = type(exc).__name__
            if "ConditionalCheckFailed" in str(exc) or "ConditionalCheckFailed" in exc_name:
                logger.warning("Duplicate audit event ignored: %s", event_id)
            else:
                logger.error("Failed to write audit event: %s", exc)
                raise AuditLogError(f"Failed to write audit event: {exc}") from exc

        return item

    def query_by_execution(self, execution_id: str) -> list[dict[str, Any]]:
        """Query all audit events for a given execution ID.

        Requires a GSI ``execution_id-index`` on the audit log table.

        Parameters
        ----------
        execution_id:
            The SFN execution ID or pipeline run ID.

        Returns
        -------
        List of audit event dicts sorted by timestamp.
        """
        table = self._get_client()
        try:
            response = table.query(
                IndexName="execution_id-index",
                KeyConditionExpression="execution_id = :eid",
                ExpressionAttributeValues={":eid": execution_id},
            )
            items = response.get("Items", [])
            return sorted(items, key=lambda x: x.get("timestamp_ms", 0))
        except Exception as exc:
            logger.error("Failed to query audit log: %s", exc)
            raise AuditLogError(f"Failed to query audit log: {exc}") from exc

    def query_by_type(
        self,
        event_type: AuditEventType,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query recent audit events of a given type.

        Requires a GSI ``event_type-index`` on the audit log table.

        Parameters
        ----------
        event_type:
            The event type to query.
        limit:
            Maximum number of results.

        Returns
        -------
        List of audit event dicts sorted by timestamp descending.
        """
        table = self._get_client()
        try:
            response = table.query(
                IndexName="event_type-index",
                KeyConditionExpression="event_type = :et",
                ExpressionAttributeValues={":et": event_type.value},
                ScanIndexForward=False,
                Limit=limit,
            )
            return response.get("Items", [])
        except Exception as exc:
            logger.error("Failed to query audit log: %s", exc)
            raise AuditLogError(f"Failed to query audit log: {exc}") from exc
```

---

### `src/agent_core/observability/alerts.py`

```python
"""SNS alert publisher for QITP Telegram notifications.

Publishes structured alert messages to an SNS topic. A downstream Lambda
(``telegram_alert/handler.py``) subscribes to the topic and forwards
messages to Telegram.

Usage::

    publisher = AlertPublisher(topic_arn="arn:aws:sns:eu-west-1:123456789012:qitp-dev-alerts")

    publisher.circuit_breaker_tripped(
        rule="daily_loss_breaker",
        details="Portfolio down -3.2% today. All trading halted for 24h.",
    )

    publisher.pipeline_failed(
        execution_id="arn:aws:states:...",
        error="Gap Detection Agent timed out after 15min",
    )

    publisher.weekly_pnl_summary(
        total_pnl_eur=1234.56,
        win_rate=0.65,
        positions_closed=8,
    )

Environment variables:
- ``QITP_ALERT_TOPIC_ARN`` -- SNS topic ARN
- ``EXECUTION_MODE`` -- current execution mode
"""
from __future__ import annotations

import json
import logging
import os
import time
from enum import Enum
from typing import Any

logger = logging.getLogger("qitp.alerts")


class AlertLevel(str, Enum):
    """Alert severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertPublisher:
    """Publishes alert messages to SNS for Telegram delivery.

    Parameters
    ----------
    topic_arn:
        SNS topic ARN. Defaults to ``QITP_ALERT_TOPIC_ARN`` env var.
    sns_client:
        Optional boto3 SNS client (injected for testing).
    """

    def __init__(
        self,
        topic_arn: str | None = None,
        sns_client: Any = None,
    ) -> None:
        self.topic_arn = topic_arn or os.getenv("QITP_ALERT_TOPIC_ARN", "")
        self._client = sns_client

    def _get_client(self) -> Any:
        """Lazily initialize the SNS client."""
        if self._client is None:
            import boto3  # type: ignore[import-untyped]

            self._client = boto3.client("sns")
        return self._client

    def publish(
        self,
        alert_type: str,
        level: AlertLevel,
        title: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> str | None:
        """Publish a structured alert to SNS.

        Parameters
        ----------
        alert_type:
            Category string (e.g. ``circuit_breaker``, ``pipeline_failure``).
        level:
            Severity level.
        title:
            Short title for the alert (used as Telegram header).
        message:
            Human-readable message body.
        details:
            Optional structured data for the alert.

        Returns
        -------
        SNS MessageId on success, None on failure.
        """
        if not self.topic_arn:
            logger.warning("No SNS topic ARN configured -- alert not sent: %s", title)
            return None

        mode = os.getenv("EXECUTION_MODE", "backtest")
        payload = {
            "alert_type": alert_type,
            "level": level.value,
            "title": title,
            "message": message,
            "execution_mode": mode,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "details": details or {},
        }

        try:
            client = self._get_client()
            response = client.publish(
                TopicArn=self.topic_arn,
                Subject=f"[QITP {mode.upper()}] {level.value}: {title}",
                Message=json.dumps(payload, default=str),
                MessageAttributes={
                    "alert_type": {
                        "DataType": "String",
                        "StringValue": alert_type,
                    },
                    "level": {
                        "DataType": "String",
                        "StringValue": level.value,
                    },
                },
            )
            msg_id = response.get("MessageId", "unknown")
            logger.info("Alert published: type=%s level=%s msg_id=%s", alert_type, level.value, msg_id)
            return msg_id
        except Exception:
            logger.exception("Failed to publish alert: %s", title)
            return None

    # ---- Convenience Methods ----

    def circuit_breaker_tripped(self, rule: str, details: str) -> str | None:
        """Alert: circuit breaker tripped."""
        return self.publish(
            alert_type="circuit_breaker",
            level=AlertLevel.CRITICAL,
            title=f"Circuit Breaker: {rule}",
            message=details,
            details={"rule": rule},
        )

    def circuit_breaker_reset(self, rule: str) -> str | None:
        """Alert: circuit breaker reset."""
        return self.publish(
            alert_type="circuit_breaker_reset",
            level=AlertLevel.INFO,
            title=f"Circuit Breaker Reset: {rule}",
            message=f"Circuit breaker '{rule}' has been manually reset.",
            details={"rule": rule},
        )

    def pipeline_failed(self, execution_id: str, error: str) -> str | None:
        """Alert: pipeline execution failed."""
        return self.publish(
            alert_type="pipeline_failure",
            level=AlertLevel.CRITICAL,
            title="Pipeline Failed",
            message=f"Execution {execution_id} failed: {error}",
            details={"execution_id": execution_id, "error": error},
        )

    def pipeline_completed(self, execution_id: str, duration_s: float) -> str | None:
        """Alert: pipeline execution completed successfully."""
        return self.publish(
            alert_type="pipeline_completed",
            level=AlertLevel.INFO,
            title="Pipeline Completed",
            message=f"Execution {execution_id} completed in {duration_s:.1f}s",
            details={"execution_id": execution_id, "duration_s": duration_s},
        )

    def weekly_pnl_summary(
        self,
        total_pnl_eur: float,
        win_rate: float,
        positions_closed: int,
        sharpe_ratio: float | None = None,
        max_drawdown_pct: float | None = None,
    ) -> str | None:
        """Alert: weekly P&L summary."""
        emoji = "+" if total_pnl_eur >= 0 else ""
        details: dict[str, Any] = {
            "total_pnl_eur": total_pnl_eur,
            "win_rate": win_rate,
            "positions_closed": positions_closed,
        }
        if sharpe_ratio is not None:
            details["sharpe_ratio"] = sharpe_ratio
        if max_drawdown_pct is not None:
            details["max_drawdown_pct"] = max_drawdown_pct

        message = (
            f"P&L: {emoji}{total_pnl_eur:.2f} EUR | "
            f"Win rate: {win_rate:.0%} | "
            f"Positions closed: {positions_closed}"
        )
        if sharpe_ratio is not None:
            message += f" | Sharpe: {sharpe_ratio:.2f}"

        return self.publish(
            alert_type="weekly_pnl",
            level=AlertLevel.INFO if total_pnl_eur >= 0 else AlertLevel.WARNING,
            title="Weekly P&L Summary",
            message=message,
            details=details,
        )

    def risk_check_failed(self, rule: str, agent_id: str, details: str) -> str | None:
        """Alert: risk check failed for an order."""
        return self.publish(
            alert_type="risk_check_fail",
            level=AlertLevel.WARNING,
            title=f"Risk Check Failed: {rule}",
            message=f"Agent {agent_id}: {details}",
            details={"rule": rule, "agent_id": agent_id},
        )
```

---

### `src/agent_core/hooks/observability_hooks.py`

```python
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
        execution_mode="backtest",
    )
    agent = Agent(..., callbacks=hooks)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agent_core.observability.audit_log import AuditEventType, AuditLogWriter
from agent_core.observability.langfuse_hook import LangfuseHook
from agent_core.observability.structured_logger import StructuredLogger

logger = logging.getLogger("qitp.hooks.observability")


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
    execution_mode: str = "backtest"
    symbol: str = ""
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
            symbol=self.symbol,
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
            symbol=self.symbol,
            strategy_id=self.strategy_id,
        )
        self._langfuse.on_agent_start(**kwargs)

        try:
            self._audit.log(
                event_type=AuditEventType.PIPELINE_STARTED,
                agent_id=self.agent_id,
                execution_mode=self.execution_mode,
                payload={
                    "symbol": self.symbol,
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
                event_type=AuditEventType.PIPELINE_COMPLETED,
                agent_id=self.agent_id,
                execution_mode=self.execution_mode,
                payload={
                    "symbol": self.symbol,
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
    execution_mode: str = "backtest",
    symbol: str = "",
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
        ``backtest``, ``paper``, or ``live``.
    symbol:
        Trading symbol (optional).
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
        symbol=symbol,
        strategy_id=strategy_id,
        audit_table=audit_table,
    )
    return [hook]
```

---

### `tccw-agent-infra/stacks/observability_stack.py` (FULL REPLACEMENT)

```python
"""Observability stack: CloudWatch dashboards, X-Ray, SNS alerts, log groups.

This replaces the skeleton from P11 with the full observability implementation.
Includes:
- 8-widget CloudWatch dashboard
- SNS topic for Telegram alerts
- Telegram alert Lambda
- X-Ray tracing group
- CloudWatch log groups for all agents/MCPs
- Metric alarms for agents, MCPs, risk engine, pipeline
"""
from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_cloudwatch as cw,
    aws_lambda as lambda_,
    aws_ecs as ecs,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subs,
    aws_cloudwatch_actions as cw_actions,
    aws_logs as logs,
    aws_iam as iam,
    aws_xray as xray,
    aws_ssm as ssm,
)


class ObservabilityStack(Stack):
    """Full observability stack for QITP platform.

    Creates:
    1. CloudWatch log groups for agents and MCPs
    2. SNS topic for alerts (Telegram delivery)
    3. Telegram alert Lambda function
    4. X-Ray tracing group
    5. CloudWatch dashboard with 8 widgets
    6. Metric alarms for error rates, latency, CPU
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        agent_functions: dict[str, lambda_.Function] | None = None,
        mcp_services: dict[str, ecs.FargateService] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        agent_functions = agent_functions or {}
        mcp_services = mcp_services or {}

        # ── Log Groups ───────────────────────────────────────────────

        agent_names = [
            "gap-detection",
            "sentiment-analysis",
            "strategy-evaluation",
            "portfolio-recommender",
            "execution",
            "risk-engine",
        ]
        self.log_groups: dict[str, logs.LogGroup] = {}

        for name in agent_names:
            lg = logs.LogGroup(
                self,
                f"LogGroup-agent-{name}",
                log_group_name=f"/qitp/{env_name}/agents/{name}",
                retention=logs.RetentionDays.ONE_YEAR,
                removal_policy=RemovalPolicy.RETAIN,
            )
            self.log_groups[f"agent-{name}"] = lg

        mcp_names = [
            "market-data",
            "sentiment",
            "artifacts",
            "backtest",
            "ibkr",
            "charting",
            "2fa",
            "ml-predict",
        ]
        for name in mcp_names:
            lg = logs.LogGroup(
                self,
                f"LogGroup-mcp-{name}",
                log_group_name=f"/qitp/{env_name}/mcps/{name}",
                retention=logs.RetentionDays.ONE_YEAR,
                removal_policy=RemovalPolicy.RETAIN,
            )
            self.log_groups[f"mcp-{name}"] = lg

        # Pipeline log group
        self.pipeline_log_group = logs.LogGroup(
            self,
            "LogGroup-pipeline",
            log_group_name=f"/qitp/{env_name}/pipeline",
            retention=logs.RetentionDays.ONE_YEAR,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── SNS Alert Topic ──────────────────────────────────────────

        self.alert_topic = sns.Topic(
            self,
            "AlertTopic",
            topic_name=f"qitp-{env_name}-alerts",
            display_name=f"QITP {env_name} Alerts",
        )

        # Export topic ARN to SSM for other stacks
        ssm.StringParameter(
            self,
            "AlertTopicArnParam",
            parameter_name=f"/qitp/{env_name}/alert-topic-arn",
            string_value=self.alert_topic.topic_arn,
        )

        # ── Telegram Alert Lambda ────────────────────────────────────

        telegram_log_group = logs.LogGroup(
            self,
            "TelegramLambdaLogGroup",
            log_group_name=f"/qitp/{env_name}/lambda/telegram-alert",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.telegram_lambda = lambda_.Function(
            self,
            "TelegramAlertLambda",
            function_name=f"qitp-{env_name}-telegram-alert",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda/telegram_alert"),
            architecture=lambda_.Architecture.ARM_64,
            timeout=Duration.seconds(30),
            memory_size=128,
            environment={
                "TELEGRAM_BOT_TOKEN_PARAM": f"/qitp/{env_name}/telegram-bot-token",
                "TELEGRAM_CHAT_ID_PARAM": f"/qitp/{env_name}/telegram-chat-id",
                "ENV_NAME": env_name,
            },
            log_group=telegram_log_group,
        )

        # Grant SSM read for Telegram secrets
        self.telegram_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:GetParameter"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/qitp/{env_name}/telegram-*",
                ],
            )
        )

        # Subscribe Lambda to SNS topic
        self.alert_topic.add_subscription(
            sns_subs.LambdaSubscription(self.telegram_lambda)
        )

        # ── X-Ray Tracing Group ──────────────────────────────────────

        self.xray_group = xray.CfnGroup(
            self,
            "XRayGroup",
            group_name=f"qitp-{env_name}",
            filter_expression=f'annotation.environment == "{env_name}"',
        )

        # ── Agent Lambda Alarms ──────────────────────────────────────

        agent_widgets: list[cw.IWidget] = []

        for name, fn in agent_functions.items():
            error_alarm = cw.Alarm(
                self,
                f"ErrorAlarm-{name}",
                alarm_name=f"qitp-{env_name}-agent-{name}-errors",
                metric=fn.metric_errors(period=Duration.minutes(5)),
                threshold=3,
                evaluation_periods=2,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            )
            error_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))

            duration_alarm = cw.Alarm(
                self,
                f"DurationAlarm-{name}",
                alarm_name=f"qitp-{env_name}-agent-{name}-duration",
                metric=fn.metric_duration(
                    period=Duration.minutes(5),
                    statistic="p99",
                ),
                threshold=600_000,  # 10 minutes in ms
                evaluation_periods=2,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            )
            duration_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))

            agent_widgets.append(
                cw.GraphWidget(
                    title=f"Agent: {name}",
                    left=[
                        fn.metric_invocations(period=Duration.minutes(5)),
                        fn.metric_errors(period=Duration.minutes(5)),
                    ],
                    right=[
                        fn.metric_duration(period=Duration.minutes(5)),
                    ],
                    width=12,
                )
            )

        # ── MCP Service Alarms ───────────────────────────────────────

        mcp_widgets: list[cw.IWidget] = []

        for name, service in mcp_services.items():
            cpu_alarm = cw.Alarm(
                self,
                f"CpuAlarm-{name}",
                alarm_name=f"qitp-{env_name}-mcp-{name}-cpu",
                metric=service.metric_cpu_utilization(
                    period=Duration.minutes(5),
                ),
                threshold=80,
                evaluation_periods=3,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            )
            cpu_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))

            mcp_widgets.append(
                cw.GraphWidget(
                    title=f"MCP: {name}",
                    left=[
                        service.metric_cpu_utilization(period=Duration.minutes(5)),
                    ],
                    right=[
                        service.metric_memory_utilization(period=Duration.minutes(5)),
                    ],
                    width=12,
                )
            )

        # ── Custom Metrics (via Metric Filters) ─────────────────────

        # Token cost metric from structured logs
        token_cost_metric = cw.Metric(
            namespace=f"QITP/{env_name}",
            metric_name="TokenCostUSD",
            dimensions_map={"Service": "agents"},
            period=Duration.hours(1),
            statistic="Sum",
        )

        # Risk check metrics
        risk_pass_metric = cw.Metric(
            namespace=f"QITP/{env_name}",
            metric_name="RiskCheckPass",
            period=Duration.hours(1),
            statistic="Sum",
        )
        risk_fail_metric = cw.Metric(
            namespace=f"QITP/{env_name}",
            metric_name="RiskCheckFail",
            period=Duration.hours(1),
            statistic="Sum",
        )

        # Pipeline execution metrics
        pipeline_started_metric = cw.Metric(
            namespace=f"QITP/{env_name}",
            metric_name="PipelineStarted",
            period=Duration.hours(1),
            statistic="Sum",
        )
        pipeline_completed_metric = cw.Metric(
            namespace=f"QITP/{env_name}",
            metric_name="PipelineCompleted",
            period=Duration.hours(1),
            statistic="Sum",
        )
        pipeline_failed_metric = cw.Metric(
            namespace=f"QITP/{env_name}",
            metric_name="PipelineFailed",
            period=Duration.hours(1),
            statistic="Sum",
        )

        # ── Dashboard (8 Widgets) ────────────────────────────────────

        self.dashboard = cw.Dashboard(
            self,
            "Dashboard",
            dashboard_name=f"qitp-{env_name}-overview",
            widgets=[
                # Row 1: Title
                [
                    cw.TextWidget(
                        markdown=f"# QITP Platform -- {env_name.upper()}",
                        width=24,
                        height=1,
                    )
                ],
                # Row 2: Widget 1 (Pipeline Executions) + Widget 2 (Agent Latency)
                [
                    # Widget 1: Pipeline Executions
                    cw.GraphWidget(
                        title="Pipeline Executions",
                        left=[
                            pipeline_started_metric,
                            pipeline_completed_metric,
                        ],
                        right=[pipeline_failed_metric],
                        width=12,
                        height=6,
                    ),
                    # Widget 2: Agent Latency (p50, p99)
                    cw.GraphWidget(
                        title="Agent Latency (p50/p99)",
                        left=[
                            cw.Metric(
                                namespace=f"QITP/{env_name}",
                                metric_name="AgentLatencyMs",
                                statistic="p50",
                                period=Duration.minutes(15),
                            ),
                            cw.Metric(
                                namespace=f"QITP/{env_name}",
                                metric_name="AgentLatencyMs",
                                statistic="p99",
                                period=Duration.minutes(15),
                            ),
                        ],
                        width=12,
                        height=6,
                    ),
                ],
                # Row 3: Widget 3 (Token Cost) + Widget 4 (Portfolio NAV)
                [
                    # Widget 3: Token Cost
                    cw.GraphWidget(
                        title="Token Cost (USD/hour)",
                        left=[token_cost_metric],
                        width=12,
                        height=6,
                    ),
                    # Widget 4: Portfolio NAV
                    cw.GraphWidget(
                        title="Portfolio NAV (EUR)",
                        left=[
                            cw.Metric(
                                namespace=f"QITP/{env_name}",
                                metric_name="PortfolioNAV",
                                statistic="Average",
                                period=Duration.hours(1),
                            ),
                        ],
                        width=12,
                        height=6,
                    ),
                ],
                # Row 4: Widget 5 (Open Positions) + Widget 6 (Risk PASS/FAIL)
                [
                    # Widget 5: Open Positions
                    cw.SingleValueWidget(
                        title="Open Positions",
                        metrics=[
                            cw.Metric(
                                namespace=f"QITP/{env_name}",
                                metric_name="OpenPositions",
                                statistic="Maximum",
                                period=Duration.minutes(5),
                            ),
                        ],
                        width=12,
                        height=4,
                    ),
                    # Widget 6: Risk PASS/FAIL
                    cw.GraphWidget(
                        title="Risk Check PASS/FAIL",
                        left=[risk_pass_metric],
                        right=[risk_fail_metric],
                        width=12,
                        height=4,
                    ),
                ],
                # Row 5: Widget 7 (2FA Approval Rate) + Widget 8 (IBKR Health)
                [
                    # Widget 7: 2FA Approval Rate
                    cw.GraphWidget(
                        title="2FA Approval Rate",
                        left=[
                            cw.Metric(
                                namespace=f"QITP/{env_name}",
                                metric_name="TwoFAApproved",
                                statistic="Sum",
                                period=Duration.hours(1),
                            ),
                            cw.Metric(
                                namespace=f"QITP/{env_name}",
                                metric_name="TwoFARejected",
                                statistic="Sum",
                                period=Duration.hours(1),
                            ),
                        ],
                        width=12,
                        height=6,
                    ),
                    # Widget 8: IBKR Health
                    cw.GraphWidget(
                        title="IBKR MCP Health",
                        left=[
                            cw.Metric(
                                namespace=f"QITP/{env_name}",
                                metric_name="IBKRHealthCheck",
                                statistic="Average",
                                period=Duration.minutes(5),
                            ),
                        ],
                        right=[
                            cw.Metric(
                                namespace=f"QITP/{env_name}",
                                metric_name="IBKRLatencyMs",
                                statistic="p99",
                                period=Duration.minutes(5),
                            ),
                        ],
                        width=12,
                        height=6,
                    ),
                ],
                # Row 6: Agent detail widgets
                [
                    cw.TextWidget(
                        markdown="## Agent Lambda Functions",
                        width=24,
                        height=1,
                    )
                ],
                agent_widgets if agent_widgets else [],
                # Row 7: MCP detail widgets
                [
                    cw.TextWidget(
                        markdown="## MCP Fargate Services",
                        width=24,
                        height=1,
                    )
                ],
                mcp_widgets if mcp_widgets else [],
            ],
        )
```

---

### `tccw-agent-infra/lambda/telegram_alert/handler.py`

```python
"""Telegram alert Lambda -- receives SNS messages and forwards to Telegram.

Environment variables:
- ``TELEGRAM_BOT_TOKEN_PARAM`` -- SSM parameter name for bot token
- ``TELEGRAM_CHAT_ID_PARAM`` -- SSM parameter name for chat ID
- ``ENV_NAME`` -- environment name for message prefix
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.parse

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Cache SSM values across warm invocations
_bot_token: str | None = None
_chat_id: str | None = None


def _get_ssm_param(name: str) -> str:
    """Fetch an SSM parameter value."""
    client = boto3.client("ssm")
    response = client.get_parameter(Name=name, WithDecryption=True)
    return response["Parameter"]["Value"]


def _get_credentials() -> tuple[str, str]:
    """Get Telegram bot token and chat ID from SSM (cached)."""
    global _bot_token, _chat_id  # noqa: PLW0603

    if _bot_token is None:
        token_param = os.environ["TELEGRAM_BOT_TOKEN_PARAM"]
        _bot_token = _get_ssm_param(token_param)

    if _chat_id is None:
        chat_param = os.environ["TELEGRAM_CHAT_ID_PARAM"]
        _chat_id = _get_ssm_param(chat_param)

    return _bot_token, _chat_id


def _format_message(alert: dict) -> str:
    """Format an alert dict as a Telegram-friendly message."""
    level = alert.get("level", "INFO")
    title = alert.get("title", "Alert")
    message = alert.get("message", "")
    mode = alert.get("execution_mode", "unknown")
    timestamp = alert.get("timestamp_iso", "")
    env_name = os.getenv("ENV_NAME", "dev")

    # Level emoji mapping
    level_icons = {
        "CRITICAL": "🔴",
        "WARNING": "🟡",
        "INFO": "🟢",
    }
    icon = level_icons.get(level, "⚪")

    lines = [
        f"{icon} *[QITP {env_name.upper()} / {mode.upper()}]*",
        f"*{title}*",
        "",
        message,
        "",
        f"_{timestamp}_",
    ]

    details = alert.get("details", {})
    if details:
        lines.append("")
        lines.append("*Details:*")
        for key, value in details.items():
            lines.append(f"  `{key}`: {value}")

    return "\n".join(lines)


def _send_telegram(bot_token: str, chat_id: str, text: str) -> dict:
    """Send a message via Telegram Bot API using urllib (no extra deps)."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        return body


def lambda_handler(event: dict, context: dict) -> dict:
    """Lambda handler: processes SNS event records and sends Telegram messages.

    Parameters
    ----------
    event:
        SNS event with ``Records`` containing ``Sns.Message`` JSON payloads.
    context:
        Lambda context (unused).

    Returns
    -------
    Dict with ``statusCode`` and ``messages_sent`` count.
    """
    bot_token, chat_id = _get_credentials()
    messages_sent = 0

    for record in event.get("Records", []):
        sns_message = record.get("Sns", {}).get("Message", "{}")

        try:
            alert = json.loads(sns_message)
        except json.JSONDecodeError:
            logger.error("Failed to parse SNS message: %s", sns_message[:200])
            continue

        text = _format_message(alert)
        logger.info("Sending Telegram message: %s", alert.get("title", "unknown"))

        try:
            result = _send_telegram(bot_token, chat_id, text)
            if result.get("ok"):
                messages_sent += 1
                logger.info("Telegram message sent: message_id=%s", result.get("result", {}).get("message_id"))
            else:
                logger.error("Telegram API error: %s", result)
        except Exception:
            logger.exception("Failed to send Telegram message")

    return {"statusCode": 200, "messages_sent": messages_sent}
```

---

## Tests

---

### `tccw-agent-core/tests/test_structured_logger.py`

```python
"""Tests for StructuredLogger."""
from __future__ import annotations

import json
import logging

import pytest

from agent_core.observability.structured_logger import LogSchema, StructuredLogger


class TestLogSchema:
    def test_to_dict(self) -> None:
        schema = LogSchema(
            timestamp="2025-01-01T00:00:00",
            level="INFO",
            message="test message",
            trace_id="trace-123",
            execution_id="exec-456",
            agent_id="gap_detector",
            prompt_version="v1.2",
            execution_mode="backtest",
            extra={"symbol": "AAPL"},
        )
        d = schema.to_dict()
        assert d["timestamp"] == "2025-01-01T00:00:00"
        assert d["level"] == "INFO"
        assert d["agent_id"] == "gap_detector"
        assert d["extra"]["symbol"] == "AAPL"

    def test_to_json(self) -> None:
        schema = LogSchema(
            timestamp="2025-01-01T00:00:00",
            level="ERROR",
            message="boom",
            trace_id="t",
            execution_id="e",
            agent_id="a",
            prompt_version="v",
            execution_mode="live",
        )
        parsed = json.loads(schema.to_json())
        assert parsed["level"] == "ERROR"
        assert "extra" not in parsed  # empty extra is omitted

    def test_empty_extra_not_in_dict(self) -> None:
        schema = LogSchema(
            timestamp="t", level="INFO", message="m",
            trace_id="t", execution_id="e", agent_id="a",
            prompt_version="v", execution_mode="backtest",
        )
        d = schema.to_dict()
        assert "extra" not in d


class TestStructuredLogger:
    def test_info_logs_json(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = StructuredLogger(
            agent_id="test_agent",
            execution_mode="backtest",
            prompt_version="v1.0",
            trace_id="trace-fixed",
            execution_id="exec-fixed",
        )
        with caplog.at_level(logging.INFO, logger="qitp.structured"):
            record = logger.info("Gap found", symbol="AAPL", gap_pct=2.3)

        assert record.agent_id == "test_agent"
        assert record.level == "INFO"
        assert record.extra["symbol"] == "AAPL"
        assert record.extra["gap_pct"] == 2.3

        # Verify the log output is valid JSON
        assert len(caplog.records) == 1
        parsed = json.loads(caplog.records[0].message)
        assert parsed["agent_id"] == "test_agent"

    def test_error_level(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = StructuredLogger(agent_id="err_agent")
        with caplog.at_level(logging.ERROR, logger="qitp.structured"):
            record = logger.error("MCP timeout", tool="market-data-mcp")

        assert record.level == "ERROR"
        assert record.extra["tool"] == "market-data-mcp"

    def test_warning_level(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = StructuredLogger(agent_id="warn_agent")
        with caplog.at_level(logging.WARNING, logger="qitp.structured"):
            record = logger.warning("Slow response")

        assert record.level == "WARNING"

    def test_debug_level(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = StructuredLogger(agent_id="dbg_agent")
        with caplog.at_level(logging.DEBUG, logger="qitp.structured"):
            record = logger.debug("Internal state", step=3)

        assert record.level == "DEBUG"
        assert record.extra["step"] == 3

    def test_critical_level(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = StructuredLogger(agent_id="crit_agent")
        with caplog.at_level(logging.CRITICAL, logger="qitp.structured"):
            record = logger.critical("System down")

        assert record.level == "CRITICAL"

    def test_defaults_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "paper")
        monkeypatch.setenv("_X_AMZN_TRACE_ID", "xray-trace-id")
        monkeypatch.setenv("SFN_EXECUTION_ID", "sfn-exec-id")
        logger = StructuredLogger(agent_id="env_agent")

        assert logger.execution_mode == "paper"
        assert logger.trace_id == "xray-trace-id"
        assert logger.execution_id == "sfn-exec-id"

    def test_auto_generated_ids(self) -> None:
        logger = StructuredLogger()
        assert len(logger.trace_id) > 0
        assert len(logger.execution_id) > 0
```

---

### `tccw-agent-core/tests/test_cost_tracker.py`

```python
"""Tests for CostTracker."""
from __future__ import annotations

import pytest

from agent_core.observability.cost_tracker import CostTracker, TokenCost


class TestCostTracker:
    def test_known_model_pricing(self) -> None:
        tracker = CostTracker()
        cost = tracker.compute_cost(
            model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            input_tokens=1000,
            output_tokens=500,
        )
        assert isinstance(cost, TokenCost)
        assert cost.input_tokens == 1000
        assert cost.output_tokens == 500
        # $0.003/1K input + $0.015/1K output
        assert abs(cost.input_cost_usd - 0.003) < 1e-8
        assert abs(cost.output_cost_usd - 0.0075) < 1e-8
        assert abs(cost.total_usd - 0.0105) < 1e-8

    def test_opus_pricing(self) -> None:
        tracker = CostTracker()
        cost = tracker.compute_cost(
            model_id="eu.anthropic.claude-opus-4-6-v1",
            input_tokens=2000,
            output_tokens=1000,
        )
        # $0.015/1K input + $0.075/1K output
        assert abs(cost.input_cost_usd - 0.030) < 1e-8
        assert abs(cost.output_cost_usd - 0.075) < 1e-8
        assert abs(cost.total_usd - 0.105) < 1e-8

    def test_unknown_model_uses_default(self) -> None:
        tracker = CostTracker()
        cost = tracker.compute_cost(
            model_id="some-future-model-v99",
            input_tokens=1000,
            output_tokens=1000,
        )
        # Default: $0.003/1K input + $0.015/1K output
        assert abs(cost.input_cost_usd - 0.003) < 1e-8
        assert abs(cost.output_cost_usd - 0.015) < 1e-8

    def test_custom_pricing(self) -> None:
        tracker = CostTracker(
            custom_pricing={"my-model": (0.001, 0.002)}
        )
        cost = tracker.compute_cost("my-model", 5000, 2000)
        assert abs(cost.input_cost_usd - 0.005) < 1e-8
        assert abs(cost.output_cost_usd - 0.004) < 1e-8
        assert abs(cost.total_usd - 0.009) < 1e-8

    def test_zero_tokens(self) -> None:
        tracker = CostTracker()
        cost = tracker.compute_cost("us.anthropic.claude-sonnet-4-20250514-v1:0", 0, 0)
        assert cost.total_usd == 0.0

    def test_to_dict(self) -> None:
        tracker = CostTracker()
        cost = tracker.compute_cost("us.anthropic.claude-sonnet-4-20250514-v1:0", 1000, 500)
        d = cost.to_dict()
        assert d["model_id"] == "us.anthropic.claude-sonnet-4-20250514-v1:0"
        assert d["input_tokens"] == 1000
        assert d["output_tokens"] == 500
        assert isinstance(d["total_usd"], float)

    def test_known_models_list(self) -> None:
        tracker = CostTracker()
        models = tracker.known_models
        assert len(models) > 5
        assert "us.anthropic.claude-sonnet-4-20250514-v1:0" in models

    def test_get_pricing(self) -> None:
        tracker = CostTracker()
        inp, out = tracker.get_pricing("amazon.nova-micro-v1:0")
        assert inp == 0.000035
        assert out == 0.00014

    def test_haiku_pricing(self) -> None:
        tracker = CostTracker()
        cost = tracker.compute_cost(
            "anthropic.claude-3-5-haiku-20241022-v1:0",
            10000,
            5000,
        )
        # $0.0008/1K input + $0.004/1K output
        assert abs(cost.input_cost_usd - 0.008) < 1e-8
        assert abs(cost.output_cost_usd - 0.020) < 1e-8
```

---

### `tccw-agent-core/tests/test_langfuse_hook.py`

```python
"""Tests for LangfuseHook.

Tests run without a real Langfuse instance -- they verify the hook's
internal tracking logic (token counts, cost, summary) and that errors
from Langfuse are handled gracefully.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from agent_core.observability.langfuse_hook import (
    LangfuseHook,
    reset_langfuse_client,
)


@pytest.fixture(autouse=True)
def _reset_langfuse():
    """Reset the global Langfuse client before each test."""
    reset_langfuse_client()
    yield
    reset_langfuse_client()


class TestLangfuseHook:
    def test_lifecycle_without_langfuse(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify hook tracks metrics even when Langfuse is not available."""
        hook = LangfuseHook(
            agent_id="gap_detector",
            prompt_id="gap_detector",
            prompt_version="v1.2",
            execution_mode="backtest",
            symbol="AAPL",
        )

        with caplog.at_level(logging.INFO, logger="qitp.langfuse"):
            hook.on_agent_start()
            hook.after_model_invocation(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                input_tokens=1000,
                output_tokens=500,
                stop_reason="end_turn",
            )
            hook.after_model_invocation(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                input_tokens=800,
                output_tokens=300,
                stop_reason="tool_use",
            )
            hook.on_agent_end()

        summary = hook.summary
        assert summary["agent_id"] == "gap_detector"
        assert summary["generation_count"] == 2
        assert summary["total_input_tokens"] == 1800
        assert summary["total_output_tokens"] == 800
        assert summary["total_cost_usd"] > 0

    def test_tags(self) -> None:
        hook = LangfuseHook(
            agent_id="sentiment",
            prompt_id="sentiment",
            prompt_version="v2.0",
            execution_mode="live",
            symbol="TSLA",
            strategy_id="gap_momentum_up",
        )
        tags = hook._tags()
        assert tags["agent_id"] == "sentiment"
        assert tags["symbol"] == "TSLA"
        assert tags["strategy_id"] == "gap_momentum_up"

    def test_tags_without_optional_fields(self) -> None:
        hook = LangfuseHook(agent_id="test")
        tags = hook._tags()
        assert "symbol" not in tags
        assert "strategy_id" not in tags

    def test_summary_initial_state(self) -> None:
        hook = LangfuseHook(agent_id="test")
        summary = hook.summary
        assert summary["generation_count"] == 0
        assert summary["total_input_tokens"] == 0
        assert summary["total_cost_usd"] == 0.0

    @patch("agent_core.observability.langfuse_hook._get_langfuse_client")
    def test_with_mock_langfuse(self, mock_get_client: MagicMock) -> None:
        """Verify Langfuse client methods are called correctly."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_client.trace.return_value = mock_trace
        mock_get_client.return_value = mock_client

        hook = LangfuseHook(agent_id="test_agent")
        hook.on_agent_start()
        hook.after_model_invocation(
            model_id="test-model",
            input_tokens=100,
            output_tokens=50,
        )
        hook.on_agent_end()

        # Verify trace was created
        mock_client.trace.assert_called_once()
        # Verify generation was logged
        mock_trace.generation.assert_called_once()
        # Verify trace was updated
        mock_trace.update.assert_called_once()
        # Verify flush was called
        mock_client.flush.assert_called_once()

    def test_cost_accumulation(self) -> None:
        hook = LangfuseHook(agent_id="cost_test")
        hook.on_agent_start()

        # 3 invocations of Sonnet
        for _ in range(3):
            hook.after_model_invocation(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                input_tokens=1000,
                output_tokens=500,
            )

        summary = hook.summary
        assert summary["generation_count"] == 3
        assert summary["total_input_tokens"] == 3000
        assert summary["total_output_tokens"] == 1500
        # 3 * ($0.003 + $0.0075) = $0.0315
        assert abs(summary["total_cost_usd"] - 0.0315) < 1e-6
```

---

### `tccw-agent-core/tests/test_xray_tracing.py`

```python
"""Tests for XRayTracer.

Tests run without aws-xray-sdk installed -- they verify the no-op fallback
behavior and the decorator pattern.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_core.observability.xray_tracing import (
    XRayTracer,
    _NoOpSubsegment,
    reset_recorder,
)


@pytest.fixture(autouse=True)
def _reset_xray():
    """Reset the global recorder before each test."""
    reset_recorder()
    yield
    reset_recorder()


class TestNoOpSubsegment:
    def test_context_manager(self) -> None:
        sub = _NoOpSubsegment()
        with sub as s:
            assert s is sub
            s.put_annotation("key", "value")
            s.put_metadata("key", "value")

    def test_add_exception(self) -> None:
        sub = _NoOpSubsegment()
        sub.add_exception(ValueError("test"))


class TestXRayTracer:
    def test_subsegment_without_sdk(self) -> None:
        """Without aws-xray-sdk, subsegment returns a no-op."""
        tracer = XRayTracer(service_name="test")
        with tracer.subsegment("test_op", symbol="AAPL") as sub:
            assert isinstance(sub, _NoOpSubsegment)
            sub.put_annotation("rows", 100)

    def test_capture_decorator_without_sdk(self) -> None:
        """Decorator works without X-Ray -- just runs the function."""
        tracer = XRayTracer(service_name="test")

        @tracer.capture("compute_gap")
        def compute_gap(a: float, b: float) -> float:
            return (a - b) / b

        result = compute_gap(105.0, 100.0)
        assert abs(result - 0.05) < 1e-6

    def test_add_annotation_without_sdk(self) -> None:
        """add_annotation is safe to call without X-Ray."""
        tracer = XRayTracer(service_name="test")
        tracer.add_annotation("key", "value")  # should not raise

    def test_add_metadata_without_sdk(self) -> None:
        """add_metadata is safe to call without X-Ray."""
        tracer = XRayTracer(service_name="test")
        tracer.add_metadata("key", {"data": 123})  # should not raise

    @patch("agent_core.observability.xray_tracing._get_recorder")
    def test_subsegment_with_mock_recorder(self, mock_get_recorder: MagicMock) -> None:
        """Verify X-Ray recorder methods are called when available."""
        mock_recorder = MagicMock()
        mock_subseg = MagicMock()
        mock_recorder.begin_subsegment.return_value = mock_subseg
        mock_get_recorder.return_value = mock_recorder

        tracer = XRayTracer(service_name="gap_detector")
        with tracer.subsegment("fetch_ohlcv", symbol="AAPL") as sub:
            assert sub is mock_subseg

        mock_recorder.begin_subsegment.assert_called_once_with("fetch_ohlcv")
        mock_subseg.put_annotation.assert_any_call("service", "gap_detector")
        mock_subseg.put_annotation.assert_any_call("symbol", "AAPL")
        mock_recorder.end_subsegment.assert_called_once()

    @patch("agent_core.observability.xray_tracing._get_recorder")
    def test_subsegment_exception_handling(self, mock_get_recorder: MagicMock) -> None:
        """Verify exceptions inside subsegments are recorded and re-raised."""
        mock_recorder = MagicMock()
        mock_subseg = MagicMock()
        mock_recorder.begin_subsegment.return_value = mock_subseg
        mock_get_recorder.return_value = mock_recorder

        tracer = XRayTracer(service_name="test")
        with pytest.raises(ValueError, match="boom"):
            with tracer.subsegment("fail_op"):
                raise ValueError("boom")

        mock_subseg.add_exception.assert_called_once()
        mock_recorder.end_subsegment.assert_called_once()
```

---

### `tccw-agent-core/tests/test_audit_log.py`

```python
"""Tests for AuditLogWriter.

Uses a mock DynamoDB table to verify write behavior, idempotency,
and validation logic.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_core.observability.audit_log import (
    AuditEventType,
    AuditLogError,
    AuditLogWriter,
    MIFID_II_RETENTION_SECONDS,
)


class MockTable:
    """Mock DynamoDB table for testing."""

    def __init__(self) -> None:
        self.items: list[dict] = []
        self._fail_next = False
        self._duplicate_next = False

    def put_item(self, Item: dict, **kwargs) -> None:
        if self._fail_next:
            self._fail_next = False
            raise RuntimeError("DynamoDB error")
        if self._duplicate_next:
            self._duplicate_next = False

            class ConditionalCheckFailedException(Exception):
                pass

            raise ConditionalCheckFailedException("ConditionalCheckFailedException")
        self.items.append(Item)

    def query(self, **kwargs) -> dict:
        return {"Items": self.items}


@pytest.fixture
def mock_table() -> MockTable:
    return MockTable()


@pytest.fixture
def writer(mock_table: MockTable) -> AuditLogWriter:
    return AuditLogWriter(
        table_name="test_audit_log",
        dynamodb_client=mock_table,
    )


class TestAuditEventType:
    def test_all_15_types(self) -> None:
        assert len(AuditEventType) == 15

    def test_values(self) -> None:
        assert AuditEventType.ORDER_REQUESTED.value == "ORDER_REQUESTED"
        assert AuditEventType.CIRCUIT_BREAKER_TRIPPED.value == "CIRCUIT_BREAKER_TRIPPED"
        assert AuditEventType.POSITION_CLOSED.value == "POSITION_CLOSED"


class TestAuditLogWriter:
    def test_write_event(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        item = writer.log(
            event_type=AuditEventType.PIPELINE_STARTED,
            agent_id="gap_detector",
            execution_mode="backtest",
            payload={"symbol": "AAPL"},
        )
        assert len(mock_table.items) == 1
        assert item["event_type"] == "PIPELINE_STARTED"
        assert item["agent_id"] == "gap_detector"
        assert item["execution_mode"] == "backtest"
        assert item["payload"]["symbol"] == "AAPL"
        assert "event_id" in item
        assert "timestamp_ms" in item
        assert "ttl" in item

    def test_ttl_is_5_years(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        import time

        now = int(time.time())
        item = writer.log(
            event_type=AuditEventType.PIPELINE_COMPLETED,
            agent_id="test",
        )
        # TTL should be ~5 years from now
        assert item["ttl"] >= now + MIFID_II_RETENTION_SECONDS - 10

    def test_idempotency_key(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        item = writer.log(
            event_type=AuditEventType.ORDER_REQUESTED,
            idempotency_key="idem-123",
            payload={"symbol": "AAPL"},
        )
        assert item["event_id"] == "idem-123"

    def test_financial_event_requires_symbol(self, writer: AuditLogWriter) -> None:
        with pytest.raises(AuditLogError, match="missing required fields"):
            writer.log(
                event_type=AuditEventType.ORDER_REQUESTED,
                payload={},  # missing "symbol"
            )

    def test_non_financial_event_no_validation(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        # PIPELINE_STARTED is not a financial event -- no symbol required
        item = writer.log(
            event_type=AuditEventType.PIPELINE_STARTED,
            payload={},
        )
        assert item["event_type"] == "PIPELINE_STARTED"

    def test_duplicate_event_ignored(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        mock_table._duplicate_next = True
        # Should not raise -- duplicates are silently ignored
        item = writer.log(
            event_type=AuditEventType.PROMPT_LOADED,
            payload={"prompt_id": "test"},
        )
        assert item["event_type"] == "PROMPT_LOADED"

    def test_dynamodb_error_raises(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        mock_table._fail_next = True
        with pytest.raises(AuditLogError, match="Failed to write"):
            writer.log(
                event_type=AuditEventType.PIPELINE_FAILED,
                payload={"error": "timeout"},
            )

    def test_default_execution_mode_from_env(
        self, mock_table: MockTable, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "live")
        writer = AuditLogWriter(table_name="test", dynamodb_client=mock_table)
        item = writer.log(event_type=AuditEventType.RISK_CHECK_PASS)
        assert item["execution_mode"] == "live"

    def test_query_by_execution(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        writer.log(
            event_type=AuditEventType.PIPELINE_STARTED,
            execution_id="exec-001",
        )
        writer.log(
            event_type=AuditEventType.PIPELINE_COMPLETED,
            execution_id="exec-001",
        )
        results = writer.query_by_execution("exec-001")
        assert len(results) == 2

    def test_query_by_type(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        writer.log(event_type=AuditEventType.RISK_CHECK_PASS)
        results = writer.query_by_type(AuditEventType.RISK_CHECK_PASS)
        assert len(results) >= 1

    def test_all_financial_events(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        """All financial events require at least 'symbol' in payload."""
        financial_events = [
            AuditEventType.ORDER_REQUESTED,
            AuditEventType.ORDER_APPROVED,
            AuditEventType.ORDER_SUBMITTED,
            AuditEventType.ORDER_FILLED,
            AuditEventType.POSITION_CLOSED,
        ]
        for evt in financial_events:
            with pytest.raises(AuditLogError):
                writer.log(event_type=evt, payload={})

            # Should succeed with symbol
            item = writer.log(event_type=evt, payload={"symbol": "AAPL"})
            assert item["event_type"] == evt.value
```

---

### `tccw-agent-core/tests/test_alerts.py`

```python
"""Tests for AlertPublisher."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from agent_core.observability.alerts import AlertLevel, AlertPublisher


class MockSnsClient:
    """Mock SNS client for testing."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self._fail_next = False

    def publish(self, **kwargs) -> dict:
        if self._fail_next:
            self._fail_next = False
            raise RuntimeError("SNS error")
        self.messages.append(kwargs)
        return {"MessageId": f"msg-{len(self.messages)}"}


@pytest.fixture
def mock_sns() -> MockSnsClient:
    return MockSnsClient()


@pytest.fixture
def publisher(mock_sns: MockSnsClient) -> AlertPublisher:
    return AlertPublisher(
        topic_arn="arn:aws:sns:eu-west-1:123456789012:test-alerts",
        sns_client=mock_sns,
    )


class TestAlertPublisher:
    def test_publish(self, publisher: AlertPublisher, mock_sns: MockSnsClient) -> None:
        msg_id = publisher.publish(
            alert_type="test",
            level=AlertLevel.INFO,
            title="Test Alert",
            message="This is a test",
        )
        assert msg_id == "msg-1"
        assert len(mock_sns.messages) == 1
        payload = json.loads(mock_sns.messages[0]["Message"])
        assert payload["alert_type"] == "test"
        assert payload["title"] == "Test Alert"

    def test_no_topic_arn_returns_none(self) -> None:
        publisher = AlertPublisher(topic_arn="")
        result = publisher.publish(
            alert_type="test",
            level=AlertLevel.INFO,
            title="No Topic",
            message="No topic ARN configured",
        )
        assert result is None

    def test_sns_error_returns_none(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        mock_sns._fail_next = True
        result = publisher.publish(
            alert_type="test",
            level=AlertLevel.CRITICAL,
            title="Error Test",
            message="Should handle gracefully",
        )
        assert result is None

    def test_circuit_breaker_tripped(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        msg_id = publisher.circuit_breaker_tripped(
            rule="daily_loss_breaker",
            details="Portfolio down -3.2% today",
        )
        assert msg_id is not None
        payload = json.loads(mock_sns.messages[0]["Message"])
        assert payload["alert_type"] == "circuit_breaker"
        assert payload["level"] == "CRITICAL"
        assert payload["details"]["rule"] == "daily_loss_breaker"

    def test_circuit_breaker_reset(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        msg_id = publisher.circuit_breaker_reset(rule="daily_loss_breaker")
        assert msg_id is not None
        payload = json.loads(mock_sns.messages[0]["Message"])
        assert payload["alert_type"] == "circuit_breaker_reset"
        assert payload["level"] == "INFO"

    def test_pipeline_failed(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        msg_id = publisher.pipeline_failed(
            execution_id="arn:aws:states:exec-123",
            error="Gap Detection Agent timed out",
        )
        assert msg_id is not None
        payload = json.loads(mock_sns.messages[0]["Message"])
        assert payload["alert_type"] == "pipeline_failure"
        assert payload["level"] == "CRITICAL"

    def test_pipeline_completed(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        msg_id = publisher.pipeline_completed(
            execution_id="exec-456",
            duration_s=123.4,
        )
        assert msg_id is not None
        payload = json.loads(mock_sns.messages[0]["Message"])
        assert payload["alert_type"] == "pipeline_completed"
        assert payload["level"] == "INFO"

    def test_weekly_pnl_positive(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        msg_id = publisher.weekly_pnl_summary(
            total_pnl_eur=1234.56,
            win_rate=0.65,
            positions_closed=8,
            sharpe_ratio=1.85,
            max_drawdown_pct=-2.1,
        )
        assert msg_id is not None
        payload = json.loads(mock_sns.messages[0]["Message"])
        assert payload["alert_type"] == "weekly_pnl"
        assert payload["level"] == "INFO"  # positive P&L
        assert payload["details"]["total_pnl_eur"] == 1234.56
        assert payload["details"]["sharpe_ratio"] == 1.85

    def test_weekly_pnl_negative(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        msg_id = publisher.weekly_pnl_summary(
            total_pnl_eur=-500.0,
            win_rate=0.30,
            positions_closed=3,
        )
        assert msg_id is not None
        payload = json.loads(mock_sns.messages[0]["Message"])
        assert payload["level"] == "WARNING"  # negative P&L

    def test_risk_check_failed(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        msg_id = publisher.risk_check_failed(
            rule="max_single_position_size",
            agent_id="execution_agent",
            details="Position AAPL would exceed 20% NAV",
        )
        assert msg_id is not None
        payload = json.loads(mock_sns.messages[0]["Message"])
        assert payload["alert_type"] == "risk_check_fail"
        assert payload["level"] == "WARNING"

    def test_message_attributes(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        publisher.publish(
            alert_type="test_type",
            level=AlertLevel.WARNING,
            title="Attr Test",
            message="Check attributes",
        )
        attrs = mock_sns.messages[0]["MessageAttributes"]
        assert attrs["alert_type"]["StringValue"] == "test_type"
        assert attrs["level"]["StringValue"] == "WARNING"
```

---

### `tccw-agent-core/tests/test_observability_hooks.py`

```python
"""Tests for CompositeObservabilityHook and create_observability_hooks."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from agent_core.hooks.observability_hooks import (
    CompositeObservabilityHook,
    create_observability_hooks,
)
from agent_core.observability.langfuse_hook import reset_langfuse_client


@pytest.fixture(autouse=True)
def _reset():
    reset_langfuse_client()
    yield
    reset_langfuse_client()


class MockAuditTable:
    """Mock DynamoDB table that records put_item calls."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def put_item(self, Item: dict, **kwargs) -> None:
        self.items.append(Item)


class TestCompositeObservabilityHook:
    def test_full_lifecycle(self, caplog: pytest.LogCaptureFixture) -> None:
        mock_table = MockAuditTable()

        hook = CompositeObservabilityHook(
            agent_id="gap_detector",
            prompt_id="gap_detector",
            prompt_version="v1.2",
            execution_mode="backtest",
            symbol="AAPL",
        )
        # Inject mock table
        hook._audit._client = mock_table

        with caplog.at_level(logging.DEBUG, logger="qitp.structured"):
            hook.on_agent_start()
            hook.after_model_invocation(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                input_tokens=1000,
                output_tokens=500,
            )
            hook.on_tool_end(tool_name="get_ohlcv")
            hook.on_tool_end(tool_name="bad_tool", error="timeout")
            hook.on_agent_end()

        # Verify audit events written
        assert len(mock_table.items) == 2  # PIPELINE_STARTED + PIPELINE_COMPLETED
        assert mock_table.items[0]["event_type"] == "PIPELINE_STARTED"
        assert mock_table.items[1]["event_type"] == "PIPELINE_COMPLETED"

        # Verify Langfuse summary
        summary = hook.langfuse_summary
        assert summary["generation_count"] == 1
        assert summary["total_input_tokens"] == 1000
        assert summary["total_output_tokens"] == 500

    def test_tool_error_tracking(self) -> None:
        hook = CompositeObservabilityHook(agent_id="test")
        hook._audit._client = MockAuditTable()

        hook.on_agent_start()
        hook.on_tool_end(tool_name="ok_tool")
        hook.on_tool_end(tool_name="bad_tool", error="failed")
        hook.on_tool_end(tool_name="ok_tool_2")
        hook.on_agent_end()

        assert hook._tool_calls == 3
        assert hook._tool_errors == 1

    def test_audit_failure_non_fatal(self, caplog: pytest.LogCaptureFixture) -> None:
        """Audit log failures should not crash the agent."""
        mock_table = MagicMock()
        mock_table.put_item.side_effect = RuntimeError("DynamoDB down")

        hook = CompositeObservabilityHook(agent_id="test")
        hook._audit._client = mock_table

        # Should not raise
        hook.on_agent_start()
        hook.on_agent_end()


class TestCreateObservabilityHooks:
    def test_returns_list(self) -> None:
        hooks = create_observability_hooks(
            agent_id="test",
            prompt_id="test",
            prompt_version="v1.0",
        )
        assert isinstance(hooks, list)
        assert len(hooks) == 1
        assert isinstance(hooks[0], CompositeObservabilityHook)

    def test_factory_params_propagated(self) -> None:
        hooks = create_observability_hooks(
            agent_id="gap_detector",
            prompt_id="gap_detector",
            prompt_version="v1.2",
            execution_mode="live",
            symbol="TSLA",
            strategy_id="gap_momentum_up",
        )
        hook = hooks[0]
        assert hook.agent_id == "gap_detector"
        assert hook.execution_mode == "live"
        assert hook.symbol == "TSLA"
        assert hook.strategy_id == "gap_momentum_up"
```

---

### `tccw-agent-infra/tests/test_observability_stack.py`

```python
"""CDK tests for ObservabilityStack."""
from __future__ import annotations

import pytest
import aws_cdk as cdk
from aws_cdk import assertions

from stacks.observability_stack import ObservabilityStack


@pytest.fixture
def app():
    return cdk.App()


@pytest.fixture
def env():
    return cdk.Environment(account="123456789012", region="eu-west-1")


class TestObservabilityStack:
    def test_creates_sns_topic(self, app, env) -> None:
        stack = ObservabilityStack(
            app, "TestObs", env=env, env_name="dev"
        )
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::SNS::Topic",
            {"TopicName": "qitp-dev-alerts"},
        )

    def test_creates_telegram_lambda(self, app, env) -> None:
        stack = ObservabilityStack(
            app, "TestObs2", env=env, env_name="dev"
        )
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "FunctionName": "qitp-dev-telegram-alert",
                "Runtime": "python3.12",
                "Handler": "handler.lambda_handler",
                "Architectures": ["arm64"],
            },
        )

    def test_creates_log_groups(self, app, env) -> None:
        stack = ObservabilityStack(
            app, "TestObs3", env=env, env_name="dev"
        )
        template = assertions.Template.from_stack(stack)
        # 6 agent + 8 MCP + 1 pipeline + 1 telegram = 16 log groups
        template.resource_count_is("AWS::Logs::LogGroup", 16)

    def test_creates_dashboard(self, app, env) -> None:
        stack = ObservabilityStack(
            app, "TestObs4", env=env, env_name="dev"
        )
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {"DashboardName": "qitp-dev-overview"},
        )

    def test_creates_xray_group(self, app, env) -> None:
        stack = ObservabilityStack(
            app, "TestObs5", env=env, env_name="dev"
        )
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::XRay::Group",
            {"GroupName": "qitp-dev"},
        )

    def test_sns_subscription(self, app, env) -> None:
        stack = ObservabilityStack(
            app, "TestObs6", env=env, env_name="dev"
        )
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::SNS::Subscription",
            {"Protocol": "lambda"},
        )

    def test_ssm_parameter_for_topic_arn(self, app, env) -> None:
        stack = ObservabilityStack(
            app, "TestObs7", env=env, env_name="dev"
        )
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {"Name": "/qitp/dev/alert-topic-arn"},
        )

    def test_telegram_lambda_ssm_policy(self, app, env) -> None:
        stack = ObservabilityStack(
            app, "TestObs8", env=env, env_name="dev"
        )
        template = assertions.Template.from_stack(stack)
        # Verify IAM policy for SSM access exists
        template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": assertions.Match.object_like({
                    "Statement": assertions.Match.array_with([
                        assertions.Match.object_like({
                            "Action": "ssm:GetParameter",
                            "Effect": "Allow",
                        })
                    ])
                })
            },
        )
```

---

## Acceptance Criteria

- [ ] `pip install -e ".[dev]"` succeeds in `tccw-agent-core` with new observability modules
- [ ] `ruff check .` passes in both repos
- [ ] `mypy src/` passes in `tccw-agent-core`
- [ ] `pytest -v` passes in `tccw-agent-core` -- all observability tests green
- [ ] `cdk synth` succeeds in `tccw-agent-infra` with updated observability stack
- [ ] `pytest -v` passes in `tccw-agent-infra` -- CDK assertion tests green
- [ ] `StructuredLogger` emits valid JSON with all required fields (timestamp, trace_id, execution_id, agent_id, prompt_version, execution_mode)
- [ ] `CostTracker` correctly computes costs for all listed Bedrock models
- [ ] `LangfuseHook` tracks token counts and costs across multiple model invocations
- [ ] `LangfuseHook` works without Langfuse installed (graceful degradation)
- [ ] `XRayTracer` works without aws-xray-sdk installed (no-op fallback)
- [ ] `AuditLogWriter` enforces idempotency via ConditionExpression
- [ ] `AuditLogWriter` validates financial events require `symbol` field
- [ ] `AuditLogWriter` sets TTL to 5 years (MiFID II compliance)
- [ ] All 15 `AuditEventType` values are defined
- [ ] `AlertPublisher` publishes structured JSON to SNS with message attributes
- [ ] `AlertPublisher` convenience methods cover: circuit_breaker_tripped, circuit_breaker_reset, pipeline_failed, pipeline_completed, weekly_pnl_summary, risk_check_failed
- [ ] `CompositeObservabilityHook` wires Langfuse + audit + structured logging together
- [ ] `create_observability_hooks()` factory returns a list suitable for Strands `callbacks=`
- [ ] CloudWatch dashboard has 8 widgets (pipeline executions, agent latency, token cost, portfolio NAV, open positions, risk PASS/FAIL, 2FA approval rate, IBKR health)
- [ ] Telegram alert Lambda reads bot token from SSM (not env var)
- [ ] No hardcoded credentials anywhere -- all secrets via env vars or SSM parameters

## Test Plan

### tccw-agent-core

```bash
cd ~/dev/tccw-agent-core
pip install -e ".[dev]"
ruff check .
mypy src/
pytest -v tests/test_structured_logger.py tests/test_cost_tracker.py tests/test_langfuse_hook.py tests/test_xray_tracing.py tests/test_audit_log.py tests/test_alerts.py tests/test_observability_hooks.py
```

### tccw-agent-infra

```bash
cd ~/dev/tccw-agent-infra
pip install -e ".[dev]"
cdk synth
pytest -v tests/test_observability_stack.py
```

## Dependencies to Add

### tccw-agent-core `pyproject.toml`

Add to `dependencies`:
```toml
"langfuse>=2.0,<3.0",          # optional -- graceful degradation if missing
"aws-xray-sdk>=2.14,<3.0",     # optional -- graceful degradation if missing
"boto3>=1.35,<2.0",             # for DynamoDB audit log + SNS alerts
```

Add to `[project.optional-dependencies]`:
```toml
observability = [
    "langfuse>=2.0,<3.0",
    "aws-xray-sdk>=2.14,<3.0",
]
```

## Commit Message

```
feat: implement full observability stack (ROOT-62)

Langfuse prompt tracking, X-Ray tracing, structured JSON logging,
DynamoDB audit log (15 event types, MiFID II 5-year retention),
token cost tracker, SNS/Telegram alerting, CloudWatch dashboards
with 8 widgets. Full test coverage.
```

## Agent Instructions

1. Start with `tccw-agent-core` -- create the `observability/` package first, then `hooks/observability_hooks.py`, then all tests.
2. Move to `tccw-agent-infra` -- replace the skeleton `observability_stack.py` with the full version, add `lambda/telegram_alert/handler.py`, add CDK tests.
3. All Langfuse and X-Ray imports are lazy-loaded with try/except -- the code MUST work when these packages are not installed.
4. DynamoDB client is injected via constructor for testability -- tests use mock tables, never real AWS.
5. SNS client is injected via constructor for testability.
6. Telegram bot token and chat ID are read from SSM parameters, NEVER from environment variables directly.
7. The `CostTracker` pricing table should be treated as a configuration concern -- it will drift as AWS updates pricing. The `custom_pricing` parameter allows overrides without code changes.
