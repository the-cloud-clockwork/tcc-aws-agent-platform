"""Observability subsystem.

Provides Langfuse integration, X-Ray tracing, structured logging,
DynamoDB audit logging, cost tracking, and SNS alerting.

All heavy dependencies (langfuse, aws_xray_sdk) are imported lazily
to reduce Lambda cold start time (~200ms saving).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_core.observability.alerts import AlertPublisher
    from agent_core.observability.audit_log import AuditLogWriter
    from agent_core.observability.cost_tracker import CostTracker
    from agent_core.observability.langfuse_hook import LangfuseHook
    from agent_core.observability.structured_logger import LogSchema, StructuredLogger
    from agent_core.observability.xray_tracing import XRayTracer

__all__ = [
    "AlertPublisher",
    "AuditLogWriter",
    "CostTracker",
    "LangfuseHook",
    "LogSchema",
    "StructuredLogger",
    "XRayTracer",
]


def __getattr__(name: str):
    """Lazy import to avoid pulling in langfuse / aws_xray_sdk at module load."""
    if name == "AlertPublisher":
        from agent_core.observability.alerts import AlertPublisher
        return AlertPublisher
    if name == "AuditLogWriter":
        from agent_core.observability.audit_log import AuditLogWriter
        return AuditLogWriter
    if name == "CostTracker":
        from agent_core.observability.cost_tracker import CostTracker
        return CostTracker
    if name == "LangfuseHook":
        from agent_core.observability.langfuse_hook import LangfuseHook
        return LangfuseHook
    if name in ("LogSchema", "StructuredLogger"):
        from agent_core.observability import structured_logger as _sl
        return getattr(_sl, name)
    if name == "XRayTracer":
        from agent_core.observability.xray_tracing import XRayTracer
        return XRayTracer
    raise AttributeError(f"module 'agent_core.observability' has no attribute {name!r}")
