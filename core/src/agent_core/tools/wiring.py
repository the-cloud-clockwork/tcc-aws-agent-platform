"""Builtin tool wiring — bridges blueprint config to runtime tool providers.

Created once per :meth:`BlueprintLoader.build_agent_session` call when the
blueprint declares ``builtin:`` tool entries.  Follows the same pattern as
:class:`~agent_core.memory.wiring.MemoryWiring`.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_core.schemas.tool_config import BuiltinToolConfig, BuiltinToolType

logger = logging.getLogger(__name__)


class BuiltinToolWiring:
    """Orchestrates builtin tool providers from blueprint configuration.

    Exposes:
    - ``tool_providers`` — flat list of Strands-compatible tool callables
    - ``start()`` / ``stop()`` — lifecycle management for all providers

    Parameters
    ----------
    configs:
        List of ``BuiltinToolConfig`` entries from the blueprint.
    region:
        Default AWS region.  Individual configs can override via their
        own ``region`` field.
    """

    def __init__(
        self,
        configs: list[BuiltinToolConfig],
        *,
        region: str,
    ) -> None:
        self._configs = configs
        self._region = region
        self._providers: list[Any] = []

        for cfg in configs:
            effective_region = cfg.region or region

            if cfg.builtin == BuiltinToolType.CODE_INTERPRETER:
                from agent_core.tools.code_interpreter import CodeInterpreterProvider

                provider = CodeInterpreterProvider(
                    region=effective_region,
                    network_mode=cfg.network_mode,
                )
                self._providers.append(provider)
                logger.info(
                    "Wired CodeInterpreterProvider (region=%s, network=%s)",
                    effective_region,
                    cfg.network_mode,
                )

            elif cfg.builtin == BuiltinToolType.BROWSER:
                from agent_core.tools.browser import BrowserProvider

                provider = BrowserProvider(region=effective_region)
                self._providers.append(provider)
                logger.info(
                    "Wired BrowserProvider (region=%s)",
                    effective_region,
                )

    @property
    def tool_providers(self) -> list[Any]:
        """Flat list of all Strands-compatible tool callables."""
        tools: list[Any] = []
        for provider in self._providers:
            tools.extend(provider.tools)
        return tools

    def start(self) -> None:
        """Start all providers that require explicit lifecycle management."""
        for provider in self._providers:
            provider.start()

    def stop(self) -> None:
        """Stop all providers (exception-safe)."""
        for provider in self._providers:
            try:
                provider.stop()
            except Exception:
                logger.exception("Error stopping provider %s", type(provider).__name__)
