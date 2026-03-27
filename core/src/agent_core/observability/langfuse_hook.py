"""Langfuse integration hook for Strands agents.

Logs every model invocation to Langfuse with structured tags: agent_id,
prompt_id, prompt_version, execution_mode, target.
Also computes token cost via CostTracker.

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

from collections.abc import Callable

from agent_core.observability.cost_tracker import CostTracker

logger = logging.getLogger("agent_core.langfuse")

# Lazy-loaded Langfuse client
_langfuse_client: Any = None


def _log(msg: str) -> None:
    logger.debug(msg)


def _get_langfuse_client() -> Any:
    """Lazily initialize the Langfuse client.

    Returns None if langfuse is not installed or not configured.
    """
    global _langfuse_client

    if _langfuse_client is not None:
        _log("Client already initialized (cached)")
        return _langfuse_client

    enabled = os.getenv("LANGFUSE_ENABLED", "true").lower()
    if enabled == "false":
        _log("DISABLED via LANGFUSE_ENABLED=false")
        return None

    host = os.environ.get("LANGFUSE_HOST", "")
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    sk = os.environ.get("LANGFUSE_SECRET_KEY", "")

    _log(f"Initializing: host={host}, pk={pk[:20]}..., sk={'set' if sk else 'EMPTY'}, enabled={enabled}")

    if not host:
        _log("LANGFUSE_HOST not set — skipping")
        return None
    if not pk:
        _log("LANGFUSE_PUBLIC_KEY not set — skipping")
        return None
    if not sk:
        _log("LANGFUSE_SECRET_KEY not set — skipping")
        return None

    try:
        from langfuse import Langfuse  # type: ignore[import-untyped]
        _log("langfuse package imported OK")

        _langfuse_client = Langfuse(
            public_key=pk,
            secret_key=sk,
            host=host,
        )
        _log(f"Langfuse client created for {host}")
        return _langfuse_client
    except ImportError as e:
        _log(f"IMPORT FAILED: {e}")
        return None
    except Exception as e:
        _log(f"INIT FAILED: {e}")
        return None


def reset_langfuse_client() -> None:
    """Reset the cached Langfuse client. Used in tests."""
    global _langfuse_client
    _langfuse_client = None


@dataclass
class LangfuseHook:
    """Strands callback hook that logs model invocations to Langfuse."""

    agent_id: str = ""
    prompt_id: str = ""
    prompt_version: str = ""
    execution_mode: str = ""
    target: str = ""

    pii_filter: Callable[[str], str] | None = None

    _trace: Any = field(default=None, init=False, repr=False)
    _generation_count: int = field(default=0, init=False, repr=False)
    _total_input_tokens: int = field(default=0, init=False, repr=False)
    _total_output_tokens: int = field(default=0, init=False, repr=False)
    _total_cost_usd: float = field(default=0.0, init=False, repr=False)
    _start_time: float = field(default=0.0, init=False, repr=False)
    _cost_tracker: CostTracker = field(
        default_factory=CostTracker, init=False, repr=False
    )
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
        _log(f"on_agent_start called for {self.agent_id}")
        self._start_time = time.monotonic()
        self._generation_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost_usd = 0.0
        self._trace_id = str(uuid.uuid4())

        client = _get_langfuse_client()
        if client is None:
            _log("on_agent_start: client is None — no trace created")
            return

        try:
            self._trace = client.trace(
                id=self._trace_id,
                name=f"agent:{self.agent_id}",
                metadata=self._tags(),
                tags=list(self._tags().values()),
            )
            _log(f"Trace created: {self._trace_id}")
        except Exception as e:
            _log(f"TRACE CREATE FAILED: {e}")
            self._trace = None

    def after_model_invocation(
        self,
        model_id: str = "unknown",
        input_tokens: int = 0,
        output_tokens: int = 0,
        stop_reason: str = "",
        **kwargs: Any,
    ) -> None:
        """Log a model generation to the current Langfuse trace."""
        self._generation_count += 1
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

        cost = self._cost_tracker.compute_cost(model_id, input_tokens, output_tokens)
        self._total_cost_usd += cost.total_usd

        _log(f"after_model_invocation #{self._generation_count}: model={model_id} in={input_tokens} out={output_tokens}")

        if self._trace is None:
            _log("after_model_invocation: trace is None — skipping generation log")
            return

        input_text = kwargs.get("input_text", "")
        output_text = kwargs.get("output_text", "")
        if self.pii_filter is not None:
            if input_text:
                input_text = self.pii_filter(input_text)
            if output_text:
                output_text = self.pii_filter(output_text)

        gen_kwargs: dict[str, Any] = {
            "name": f"generation-{self._generation_count}",
            "model": model_id,
            "model_parameters": {"stop_reason": stop_reason},
            "usage": {
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
                "unit": "TOKENS",
            },
            "metadata": {
                **self._tags(),
                "cost_usd": cost.total_usd,
                "generation_number": self._generation_count,
            },
        }
        if input_text:
            gen_kwargs["input"] = input_text
        if output_text:
            gen_kwargs["output"] = output_text

        try:
            self._trace.generation(**gen_kwargs)
            _log(f"Generation #{self._generation_count} logged to Langfuse")
        except Exception as e:
            _log(f"GENERATION LOG FAILED: {e}")

    def on_agent_end(self, **kwargs: Any) -> None:
        """Finalize the Langfuse trace with summary metadata."""
        elapsed = time.monotonic() - self._start_time if self._start_time else 0.0

        _log(
            f"on_agent_end: {self.agent_id} generations={self._generation_count} "
            f"in={self._total_input_tokens} out={self._total_output_tokens} "
            f"cost=${self._total_cost_usd:.6f} elapsed={elapsed:.3f}s"
        )

        if self._trace is None:
            _log("on_agent_end: trace is None — skipping update + flush")
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
            _log("Trace updated")
        except Exception as e:
            _log(f"TRACE UPDATE FAILED: {e}")

        try:
            client = _get_langfuse_client()
            if client:
                client.flush()
                _log("Langfuse flushed OK")
        except Exception as e:
            _log(f"FLUSH FAILED: {e}")

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
