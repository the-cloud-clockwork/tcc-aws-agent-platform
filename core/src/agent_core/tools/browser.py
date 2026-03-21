"""Browser provider — Gateway-mediated builtin tool.

All builtin tools are registered as Gateway targets.  The Gateway proxies
calls to the managed Browser service, so there is no local SDK
instantiation.  This provider discovers Browser tools from the Gateway
and exposes them for the agent.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_core.gateway.client import GatewayClient

logger = logging.getLogger(__name__)

# Gateway target name for the managed Browser service.
BROWSER_TARGET = "browser"


class BrowserProvider:
    """Gateway-backed provider for the AgentCore Browser tool.

    Discovers Browser tools from the Gateway rather than creating a local
    SDK client.  The Gateway manages the browser lifecycle.

    Parameters
    ----------
    gateway_client:
        Active ``GatewayClient`` connected to the AgentCore Gateway.
    """

    def __init__(self, *, gateway_client: GatewayClient) -> None:
        self._gateway = gateway_client
        self._cached_tools: list[Any] | None = None

    def start(self) -> None:
        """No-op — Gateway manages Browser lifecycle."""

    def stop(self) -> None:
        """No-op — Gateway manages Browser lifecycle."""

    @property
    def tools(self) -> list[Any]:
        """Return Browser tools discovered from the Gateway.

        Tools are cached after first discovery to avoid repeated
        round-trips to the Gateway.
        """
        if self._cached_tools is not None:
            return self._cached_tools

        all_tools = self._gateway.list_tools_sync()
        browser_tools = [
            t for t in all_tools if _tool_matches_target(t, BROWSER_TARGET)
        ]
        self._cached_tools = browser_tools
        logger.info(
            "Discovered %d Browser tool(s) from Gateway",
            len(browser_tools),
        )
        return browser_tools


def _tool_matches_target(tool: Any, target: str) -> bool:
    """Check whether a Gateway tool belongs to the given target namespace."""
    name = (
        getattr(tool, "name", "")
        if not isinstance(tool, dict)
        else tool.get("name", "")
    )
    return name.startswith(f"{target}::")
