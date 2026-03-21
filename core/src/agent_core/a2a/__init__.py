"""A2A (Agent-to-Agent) communication subsystem.

Provides cross-runtime agent discovery and invocation via the A2A protocol
(agent cards + standardized messaging) and direct invoke_agent_runtime().
"""

from __future__ import annotations


def __getattr__(name: str):
    """Lazy imports to avoid loading strands.multiagent.a2a at import time."""
    if name == "A2AClient":
        from agent_core.a2a.client import A2AClient

        return A2AClient
    if name == "A2AServerWrapper":
        from agent_core.a2a.server import A2AServerWrapper

        return A2AServerWrapper
    if name == "remote_agent_tool":
        from agent_core.a2a.tools import remote_agent_tool

        return remote_agent_tool
    if name == "A2AWiring":
        from agent_core.a2a.wiring import A2AWiring

        return A2AWiring
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "A2AClient",
    "A2AServerWrapper",
    "A2AWiring",
    "remote_agent_tool",
]
