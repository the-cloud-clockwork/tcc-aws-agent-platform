"""Code Interpreter provider — Gateway-mediated builtin tool.

All builtin tools are registered as Gateway targets.  The Gateway proxies
calls to the managed Code Interpreter service, so there is no local SDK
instantiation.  This provider discovers Code Interpreter tools from the
Gateway and exposes them for the agent.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_core.gateway.client import GatewayClient

logger = logging.getLogger(__name__)

# Gateway target name for the managed Code Interpreter service.
CODE_INTERPRETER_TARGET = "code-interpreter"


class CodeInterpreterProvider:
    """Gateway-backed provider for the AgentCore Code Interpreter.

    Discovers Code Interpreter tools from the Gateway rather than creating
    a local SDK client.  The Gateway manages sandbox lifecycle.

    Parameters
    ----------
    gateway_client:
        Active ``GatewayClient`` connected to the AgentCore Gateway.
    """

    def __init__(self, *, gateway_client: GatewayClient) -> None:
        self._gateway = gateway_client
        self._cached_tools: list[Any] | None = None

    def start(self) -> None:
        """No-op — Gateway manages Code Interpreter lifecycle."""

    def stop(self) -> None:
        """No-op — Gateway manages Code Interpreter lifecycle."""

    @property
    def tools(self) -> list[Any]:
        """Return Code Interpreter tools discovered from the Gateway.

        Tools are cached after first discovery to avoid repeated
        round-trips to the Gateway.
        """
        if self._cached_tools is not None:
            return self._cached_tools

        all_tools = self._gateway.list_tools_sync()
        ci_tools = [
            t for t in all_tools if _tool_matches_target(t, CODE_INTERPRETER_TARGET)
        ]
        self._cached_tools = ci_tools
        logger.info(
            "Discovered %d Code Interpreter tool(s) from Gateway",
            len(ci_tools),
        )
        return ci_tools


def _tool_matches_target(tool: Any, target: str) -> bool:
    """Check whether a Gateway tool belongs to the given target namespace."""
    name = (
        getattr(tool, "name", "")
        if not isinstance(tool, dict)
        else tool.get("name", "")
    )
    return name.startswith(f"{target}::")
