"""Langfuse integration hook for Strands agents.

Logs every model invocation to Langfuse with structured tags: agent_id,
prompt_id, prompt_version, execution_mode, target.
Also computes token cost via CostTracker.

Usage::

    hook = LangfuseHook(
        agent_id="my_agent",
        prompt_id="my_agent",
        prompt_version="v1.2",
        execution_mode="simulation",
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

logger = logging.getLogger("agent_core.langfuse")

# Lazy-loaded Langfuse client
_langfuse_client: Any = None


def _get_langfuse_client() -> Any:
    """Lazily initialize the Langfuse client.

    Returns None if langfuse is not installed or not configured.
    """
    global _langfuse_client

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
    global _langfuse_client
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
        One of ``simulation``, ``staging``, ``production``.
    target:
        Target entity being processed (optional).
    """

    agent_id: str = "unknown"
    prompt_id: str = "unknown"
    prompt_version: str = "unknown"
    execution_mode: str = "simulation"
    target: str = ""

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
        if self.target:
            tags["target"] = self.target
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
