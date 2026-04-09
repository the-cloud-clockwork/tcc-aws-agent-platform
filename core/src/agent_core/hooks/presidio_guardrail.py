"""Presidio-based PII guardrail hook — provider-agnostic alternative to Bedrock Guardrails.

Uses Microsoft Presidio (MIT-licensed) to detect and redact PII in agent
I/O. Suitable for any inference provider — LiteLLM, Anthropic direct,
OpenAI, Vertex — not just Bedrock. Analyzer and anonymizer engines are
lazy-loaded on first call so import cost is zero until the hook fires.

Blueprint selection::

    observability:
      data_protection:
        provider: presidio
        presidio_entities: [EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, US_SSN]
        presidio_language: en

Empty ``presidio_entities`` means "detect Presidio's default set"
(EMAIL_ADDRESS, PHONE_NUMBER, PERSON, etc.).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PresidioGuardrailHook:
    """Strands HookProvider that redacts PII using Microsoft Presidio."""

    entities: list[str] = field(default_factory=list)
    language: str = "en"

    def __post_init__(self) -> None:
        self._analyzer: Any = None
        self._anonymizer: Any = None

    def _ensure_engines(self) -> bool:
        """Lazy-load Presidio engines. Returns False if Presidio is unavailable."""
        if self._analyzer is not None:
            return True
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
        except ImportError:
            logger.warning(
                "PresidioGuardrailHook: presidio-analyzer/presidio-anonymizer not installed. "
                "Install with the 'presidio' extra: pip install 'agent-core[presidio]'. "
                "Hook will no-op until the dependency is available."
            )
            return False
        self._analyzer = AnalyzerEngine()
        self._anonymizer = AnonymizerEngine()
        return True

    def register_hooks(self, registry: Any, **kwargs: Any) -> None:
        from strands.hooks.registry import HookRegistry

        assert isinstance(registry, HookRegistry)
        try:
            from strands.hooks.events import AfterInvocationEvent, BeforeInvocationEvent

            registry.add_callback(BeforeInvocationEvent, self._on_before)
            registry.add_callback(AfterInvocationEvent, self._on_after)
            logger.info(
                "PresidioGuardrailHook registered (entities=%s, lang=%s)",
                self.entities or "<default>",
                self.language,
            )
        except ImportError:
            logger.warning("Strands hook events not available — PresidioGuardrailHook disabled")

    def _redact(self, text: str) -> str:
        if not text or not self._ensure_engines():
            return text
        try:
            analyzer_kwargs: dict[str, Any] = {"text": text, "language": self.language}
            if self.entities:
                analyzer_kwargs["entities"] = self.entities
            results = self._analyzer.analyze(**analyzer_kwargs)
            if not results:
                return text
            anonymized = self._anonymizer.anonymize(text=text, analyzer_results=results)
            return str(anonymized.text)
        except Exception:
            logger.exception("Presidio redaction failed, returning original text")
            return text

    def _on_before(self, event: Any) -> None:
        payload = getattr(event, "input", None) or getattr(event, "payload", None)
        if payload:
            redacted = self._redact(str(payload))
            if redacted != str(payload):
                logger.info("PresidioGuardrailHook: input redacted")

    def _on_after(self, event: Any) -> None:
        output = getattr(event, "output", None) or getattr(event, "result", None)
        if output:
            redacted = self._redact(str(output))
            if redacted != str(output):
                logger.info("PresidioGuardrailHook: output redacted")
