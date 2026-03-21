"""Browser provider — wraps AgentCore Browser as a Strands tool."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BrowserProvider:
    """Managed provider for the AgentCore Browser tool.

    Wraps ``strands_tools.browser.AgentCoreBrowser`` and exposes its
    callable as a Strands-compatible tool.

    Parameters
    ----------
    region:
        AWS region where the Browser service is provisioned.
    """

    def __init__(self, *, region: str) -> None:
        from strands_tools.browser import AgentCoreBrowser

        self._region = region
        self._browser = AgentCoreBrowser(region=region)
        logger.info("BrowserProvider initialised (region=%s)", region)

    def start(self) -> None:
        """No-op — AgentCoreBrowser manages its own lifecycle."""

    def stop(self) -> None:
        """No-op — AgentCoreBrowser manages its own lifecycle."""

    @property
    def tools(self) -> list[Any]:
        """Return Strands-compatible tool callables for the browser."""
        return [self._browser.browser]
