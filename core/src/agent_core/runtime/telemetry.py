"""One-shot OTEL telemetry setup for Langfuse integration.

Called once in GenericHandler.__init__. Only activates when
OTEL_EXPORTER_OTLP_ENDPOINT is set (i.e. Langfuse is configured).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_initialized = False


def setup_langfuse_otel() -> None:
    """Initialize Strands OTEL exporter if Langfuse endpoint is configured."""
    global _initialized
    if _initialized:
        return

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        logger.debug("OTEL_EXPORTER_OTLP_ENDPOINT not set — Langfuse OTEL disabled")
        _initialized = True
        return

    try:
        from strands.telemetry import StrandsTelemetry

        telemetry = StrandsTelemetry()
        telemetry.setup_otlp_exporter()
        logger.info("Langfuse OTEL exporter initialized: %s", endpoint)
    except ImportError:
        logger.warning("strands.telemetry not available — install strands-agents[otel]")
    except Exception:
        logger.exception("Failed to initialize Langfuse OTEL exporter")

    _initialized = True
