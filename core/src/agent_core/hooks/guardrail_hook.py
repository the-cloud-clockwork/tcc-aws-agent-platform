"""Bedrock Guardrail hook for agent I/O content filtering.

Applies ``sanitize_text()`` from the data protection module on agent
input (before invocation) and output (after invocation).  No-op when
the guardrail env var is not configured.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agent_core.observability.data_protection import sanitize_text
from agent_core.schemas.observability_config import DataProtectionConfig

logger = logging.getLogger(__name__)


@dataclass
class GuardrailHook:
    """Strands HookProvider that enforces Bedrock Guardrails on agent I/O."""

    config: DataProtectionConfig

    def register_hooks(self, registry: Any, **kwargs: Any) -> None:
        from strands.hooks.registry import HookRegistry

        assert isinstance(registry, HookRegistry)
        try:
            from strands.hooks.events import AfterInvocationEvent, BeforeInvocationEvent

            registry.add_callback(BeforeInvocationEvent, self._on_before)
            registry.add_callback(AfterInvocationEvent, self._on_after)
            logger.info("GuardrailHook registered for I/O content filtering")
        except ImportError:
            logger.warning("Strands hook events not available — GuardrailHook disabled")

    def _on_before(self, event: Any) -> None:
        payload = getattr(event, "input", None) or getattr(event, "payload", None)
        if payload:
            sanitized = sanitize_text(str(payload), self.config, source="INPUT")
            if sanitized != str(payload):
                logger.info("GuardrailHook: input sanitized by guardrail")

    def _on_after(self, event: Any) -> None:
        output = getattr(event, "output", None) or getattr(event, "result", None)
        if output:
            sanitized = sanitize_text(str(output), self.config, source="OUTPUT")
            if sanitized != str(output):
                logger.info("GuardrailHook: output sanitized by guardrail")
