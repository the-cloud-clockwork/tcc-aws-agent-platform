"""X-Ray distributed tracing helpers.

Provides a thin wrapper around ``aws_xray_sdk`` to create custom segments
and subsegments for agent reasoning steps, MCP calls, and pipeline stages.

Usage::

    tracer = XRayTracer(service_name="my_agent")

    with tracer.subsegment("fetch_data", target="ENTITY-1") as sub:
        data = mcp_client.call("get_data", target="ENTITY-1")
        sub.put_annotation("rows", len(data))

    # Or as a decorator
    @tracer.capture("process_data")
    def process_data(input_value, threshold):
        return input_value / threshold

Environment variables:
- ``AWS_XRAY_DAEMON_ADDRESS`` -- X-Ray daemon address (set by Lambda runtime)
- ``AWS_XRAY_SDK_ENABLED`` -- set to ``false`` to disable (default: ``true``)
- ``_X_AMZN_TRACE_ID`` -- trace ID injected by Lambda/API Gateway
"""

from __future__ import annotations

import functools
import logging
import os
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("agent_core.xray")

# Lazy-loaded X-Ray recorder
_recorder: Any = None


def _get_recorder() -> Any:
    """Lazily initialize the X-Ray recorder.

    Returns None if aws-xray-sdk is not installed or disabled.
    """
    global _recorder

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
    global _recorder
    _recorder = None


class _NoOpSubsegment:
    """Dummy subsegment when X-Ray is disabled."""

    def put_annotation(self, key: str, value: Any) -> None: ...  # No-op: X-Ray disabled

    def put_metadata(
        self, key: str, value: Any, namespace: str = "default"
    ) -> None: ...  # No-op: X-Ray disabled

    def add_exception(
        self, exception: Exception, stack: Any = None
    ) -> None: ...  # No-op: X-Ray disabled

    def __enter__(self) -> _NoOpSubsegment:
        return self

    def __exit__(self, *args: Any) -> None: ...  # No-op: X-Ray disabled


class XRayTracer:
    """Wrapper around aws_xray_sdk for distributed tracing.

    Parameters
    ----------
    service_name:
        Name of the service for annotations (e.g. ``my_agent``).
    """

    def __init__(self, service_name: str = "agent-core") -> None:
        self.service_name = service_name

    @contextmanager
    def subsegment(self, name: str, **annotations: Any) -> Generator[Any, None, None]:
        """Create a named X-Ray subsegment with optional annotations.

        Parameters
        ----------
        name:
            Subsegment name (e.g. ``fetch_data``, ``run_analytics``).
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
        except Exception:
            logger.debug("X-Ray subsegment creation failed -- falling back to no-op")
            yield _NoOpSubsegment()
            return

        if subseg is None:
            yield _NoOpSubsegment()
            return

        try:
            subseg.put_annotation("service", self.service_name)
            for key, value in annotations.items():
                subseg.put_annotation(key, value)
        except Exception:
            logger.debug("X-Ray annotation failed -- continuing with subsegment")

        try:
            yield subseg
        except Exception as exc:
            subseg.add_exception(exc, exc.__traceback__)
            raise
        finally:
            recorder.end_subsegment()

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

    def add_metadata(self, key: str, value: Any, namespace: str = "") -> None:
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
