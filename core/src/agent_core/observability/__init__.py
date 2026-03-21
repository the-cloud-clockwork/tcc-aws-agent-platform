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
    from agent_core.observability.dashboard import deploy_dashboard, generate_dashboard_body
    from agent_core.observability.data_protection import (
        apply_log_data_protection,
        build_data_protection_policy,
        build_guardrail_model_kwargs,
    )
    from agent_core.observability.langfuse_hook import LangfuseHook
    from agent_core.observability.otel import (
        build_trace_attributes,
        detach_session_baggage,
        get_agent_tracer,
        set_session_baggage,
    )
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
    "build_trace_attributes",
    "set_session_baggage",
    "detach_session_baggage",
    "get_agent_tracer",
    "build_guardrail_model_kwargs",
    "build_data_protection_policy",
    "apply_log_data_protection",
    "generate_dashboard_body",
    "deploy_dashboard",
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
    # -- OTEL module --
    if name in ("build_trace_attributes", "set_session_baggage", "detach_session_baggage", "get_agent_tracer"):
        from agent_core.observability import otel as _otel
        return getattr(_otel, name)
    # -- Data protection --
    if name in ("build_guardrail_model_kwargs", "build_data_protection_policy", "apply_log_data_protection"):
        from agent_core.observability import data_protection as _dp
        return getattr(_dp, name)
    # -- Dashboard --
    if name in ("generate_dashboard_body", "deploy_dashboard"):
        from agent_core.observability import dashboard as _dash
        return getattr(_dash, name)
    raise AttributeError(f"module 'agent_core.observability' has no attribute {name!r}")
