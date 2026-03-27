"""One-shot telemetry setup — sends a probe trace via Langfuse SDK on init.

Called once in GenericHandler.__init__. Only activates when
LANGFUSE_HOST is set.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_initialized = False


def setup_langfuse_otel() -> None:
    """Send a probe trace via Langfuse SDK to verify connectivity."""
    global _initialized
    if _initialized:
        return

    host = os.environ.get("LANGFUSE_HOST", "")
    if not host:
        logger.debug("LANGFUSE_HOST not set — Langfuse disabled")
        _initialized = True
        return

    try:
        from langfuse import Langfuse

        lf = Langfuse(
            public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
            host=host,
        )
        agent_id = os.environ.get("AGENT_ID", "unknown")
        trace = lf.trace(
            name=f"runtime-init:{agent_id}",
            tags=["probe", "init"],
            metadata={"agent_id": agent_id, "source": "GenericHandler.__init__"},
        )
        trace.generation(
            name="init-probe",
            model="probe",
            usage={"input": 0, "output": 0},
        )
        lf.flush()
        logger.info("Langfuse probe trace sent for %s to %s", agent_id, host)
    except Exception:
        logger.exception("Failed to send Langfuse probe trace")

    _initialized = True
