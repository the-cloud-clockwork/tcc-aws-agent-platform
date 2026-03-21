"""Builtin tool wiring — bridges blueprint config to Gateway-backed tool providers.

Created once per :meth:`BlueprintLoader.build_agent_session` call when the
blueprint declares ``builtin:`` tool entries.  All builtin tools are resolved
through the AgentCore Gateway — no local SDK instantiation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agent_core.schemas.tool_config import BuiltinToolConfig, BuiltinToolType

if TYPE_CHECKING:
    from agent_core.gateway.client import GatewayClient

logger = logging.getLogger(__name__)


class BuiltinToolWiring:
    """Orchestrates Gateway-backed builtin tool providers from blueprint config.

    Exposes:
    - ``tool_providers`` — flat list of tools discovered from the Gateway
    - ``start()`` / ``stop()`` — no-ops (Gateway manages lifecycle)

    Parameters
    ----------
    configs:
        List of ``BuiltinToolConfig`` entries from the blueprint.
    gateway_client:
        Active ``GatewayClient`` for tool discovery.
    """

    def __init__(
        self,
        configs: list[BuiltinToolConfig],
        *,
        gateway_client: GatewayClient,
    ) -> None:
        self._configs = configs
        self._gateway = gateway_client
        self._providers: list[Any] = []

        for cfg in configs:
            if cfg.builtin == BuiltinToolType.CODE_INTERPRETER:
                from agent_core.tools.code_interpreter import CodeInterpreterProvider

                provider = CodeInterpreterProvider(gateway_client=gateway_client)
                self._providers.append(provider)
                logger.info("Wired CodeInterpreterProvider (Gateway-backed)")

            elif cfg.builtin == BuiltinToolType.BROWSER:
                from agent_core.tools.browser import BrowserProvider

                provider = BrowserProvider(gateway_client=gateway_client)
                self._providers.append(provider)
                logger.info("Wired BrowserProvider (Gateway-backed)")

    @property
    def tool_providers(self) -> list[Any]:
        """Flat list of all builtin tools discovered from the Gateway."""
        tools: list[Any] = []
        for provider in self._providers:
            tools.extend(provider.tools)
        return tools

    def start(self) -> None:
        """No-op — Gateway manages builtin tool lifecycle."""
        for provider in self._providers:
            provider.start()

    def stop(self) -> None:
        """No-op — Gateway manages builtin tool lifecycle."""
        for provider in self._providers:
            try:
                provider.stop()
            except Exception:
                logger.exception("Error stopping provider %s", type(provider).__name__)
