"""OTEL instrumentation helpers for AgentCore agents.

Provides:
  - Session baggage (session.id, user.id correlation across spans)
  - Tracer factory (agent-scoped OTEL tracers for custom spans)
  - trace_attributes builder (merge blueprint + runtime context)

Requires ``aws-opentelemetry-distro`` to be installed in the container.
Set ``runtime.observability_enabled: true`` in the blueprint to install
it automatically in the generated Dockerfile.
"""

from __future__ import annotations

import os

try:
    from opentelemetry import baggage, context, trace
except ImportError as exc:
    raise ImportError(
        "OpenTelemetry SDK not found. Ensure aws-opentelemetry-distro is installed "
        "in the container image (set runtime.observability_enabled: true in blueprint)."
    ) from exc


def set_session_baggage(
    session_id: str,
    user_id: str | None = None,
) -> object:
    """Set OTEL baggage for session correlation.

    Every downstream span and log entry inherits these values,
    enabling session-level filtering in CloudWatch and Langfuse.

    Args:
        session_id: AgentCore session identifier.
        user_id: Optional user identifier for per-user tracing.

    Returns:
        A context token — pass to :func:`detach_session_baggage` when done.
    """
    ctx = baggage.set_baggage("session.id", session_id)
    if user_id:
        ctx = baggage.set_baggage("user.id", user_id, context=ctx)
    return context.attach(ctx)


def detach_session_baggage(token: object) -> None:
    """Detach a previously set baggage context.

    Args:
        token: The token returned by :func:`set_session_baggage`.
    """
    context.detach(token)


def get_agent_tracer(agent_name: str, version: str = "1.0.0") -> trace.Tracer:
    """Get an OTEL tracer scoped to an agent.

    Use this inside ``@tool`` functions for custom span creation::

        tracer = get_agent_tracer("my-agent")

        @tool
        def search(query: str) -> str:
            with tracer.start_as_current_span("search") as span:
                span.set_attribute("search.query", query)
                return do_search(query)

    Args:
        agent_name: Agent identifier (becomes the tracer instrumentation scope).
        version: Tracer version string.
    """
    return trace.get_tracer(agent_name, version)


def build_trace_attributes(
    blueprint_attrs: dict[str, str],
    agent_name: str,
    agent_version: str,
    execution_mode: str | None = None,
) -> dict[str, str]:
    """Merge blueprint trace_attributes with runtime context.

    The resulting dict is passed to ``Agent(trace_attributes=...)``,
    which attaches these attributes to every OTEL span the agent produces.

    Runtime attributes (agent.name, agent.version, execution.mode) are
    set first; blueprint-declared attributes override if there's a conflict.

    Args:
        blueprint_attrs: Static attributes from the ``observability.trace_attributes`` block.
        agent_name: Agent ID from the blueprint.
        agent_version: Agent version from the blueprint.
        execution_mode: Current execution mode (simulation/staging/production).
    """
    attrs: dict[str, str] = {
        "agent.name": agent_name,
        "agent.version": agent_version,
    }
    if execution_mode:
        attrs["execution.mode"] = execution_mode
    else:
        mode = os.environ.get("EXECUTION_MODE")
        if mode:
            attrs["execution.mode"] = mode

    attrs.update(blueprint_attrs)
    return attrs
