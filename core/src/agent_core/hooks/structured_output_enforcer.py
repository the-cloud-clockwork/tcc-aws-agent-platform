"""Structured Output Enforcer — provider-agnostic post-processing hook.

Why this exists
---------------
Strands SDK's ``structured_output_model`` / blueprint ``output_schema`` uses a
forced tool-call pattern that only works reliably with Bedrock's Converse API.
When the model provider is LiteLLM (or anything OpenAI-compatible), the forced
``tool_choice="required"`` doesn't guarantee the model will invoke the tool,
and Strands raises ``StructuredOutputException`` on the second retry.

Root cause trace (strands-agents 1.35.0):
    event_loop.py:215 — if stop_reason == "end_turn" AND force_attempted:
        raise StructuredOutputException("The model failed to invoke the
        structured output tool even after it was forced.")

Tracked upstream in issues #743, #1005, #891 — the fixes only cover the
deprecated ``agent.structured_output_async()`` path, not the blueprint
``output_schema`` field which goes through the event loop.

How this solves it
------------------
Instead of fighting the event loop, we run the agent normally (no
``structured_output_model`` passed to ``Agent()``), let it use its MCP tools
freely, and post-process the final message via the ``instructor`` library
which validates any OpenAI-compatible response against a Pydantic schema
with automatic retry-on-validation-error.

Instructor works by:
1. Injecting the JSON schema into the prompt
2. Calling the model's raw client
3. Parsing the response with ``pydantic.model_validate_json()``
4. On failure, re-prompting the model with the validation error

This is purely provider-agnostic — works with any OpenAI-compatible endpoint
(LiteLLM proxy, vLLM, Ollama, OpenAI itself). No Strands internal coupling.

Content replacement behaviour
-----------------------------
On success, the enforcer REPLACES the final assistant message content with
only the validated toolUse block. Any placeholder/error text produced by
upstream layers (e.g. ``[Error 400]`` synthesised when a tool errors or the
model's fallback response wasn't a valid tool call) is discarded. If the
original content contained real human-readable text alongside the placeholder,
the non-placeholder text is preserved ahead of the injected toolUse so the
agent's reasoning is still visible downstream.

See also: ``operator/inference-migration.md`` Stage 2.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Placeholder/error text patterns that upstream layers (Strands event loop,
# LiteLLM adapter) synthesise when a tool call or model response goes
# sideways. When the ONLY text in the final message matches one of these,
# we strip it because it adds no value next to the validated toolUse.
_PLACEHOLDER_TEXT_PATTERNS = (
    re.compile(r"^\s*\[Error\s+\d+\]\s*$", re.IGNORECASE),
    re.compile(r"^\s*\[No\s+response\]\s*$", re.IGNORECASE),
    re.compile(r"^\s*\(no\s+text\)\s*$", re.IGNORECASE),
)


@dataclass
class StructuredOutputEnforcer:
    """Strands HookProvider that enforces Pydantic schema on final output.

    Registers on ``AfterInvocationEvent``. Reads the final assistant message
    text, passes it to instructor with the target Pydantic model, and injects
    the validated output back into the agent result as a synthetic toolUse
    block (matching the shape Bedrock agents produce natively).
    """

    schema: type[BaseModel]
    model_id: str
    base_url: str | None = None
    api_key_env: str | None = None
    extra_headers_env: dict[str, str] | None = None
    max_retries: int = 3
    _agent_ref: Any = field(default=None, init=False)

    def register_hooks(self, registry: Any, **kwargs: Any) -> None:
        from strands.hooks.registry import HookRegistry

        assert isinstance(registry, HookRegistry)
        try:
            from strands.hooks.events import AfterInvocationEvent

            registry.add_callback(AfterInvocationEvent, self._on_after)
            logger.info(
                "StructuredOutputEnforcer registered for schema %s",
                self.schema.__name__,
            )
        except ImportError:
            logger.warning(
                "Strands hook events not available — StructuredOutputEnforcer disabled"
            )

    def _build_client(self, *, use_tools: bool = True) -> Any:
        """Lazily construct an instructor-wrapped OpenAI client.

        Defaults to ``Mode.TOOLS`` (function-calling) because the JSON mode was
        unreliable on LiteLLM-fronted Claude — when the agent's response was
        pure markdown, instructor's JSON-mode extraction failed silently after
        retries and the synthetic typed toolUse never landed in messages[-1].
        Tools mode lets the model return the schema as a first-class tool call
        rather than coaxing JSON out of free-form text.
        """
        import instructor
        from openai import OpenAI

        client_kwargs: dict[str, Any] = {}
        if self.api_key_env:
            key = os.environ.get(self.api_key_env, "")
            if key:
                client_kwargs["api_key"] = key
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        if self.extra_headers_env:
            headers = {}
            for header_name, env_var in self.extra_headers_env.items():
                val = os.environ.get(env_var, "")
                if val:
                    headers[header_name] = val
            if headers:
                client_kwargs["default_headers"] = headers

        raw_client = OpenAI(**client_kwargs)
        mode = instructor.Mode.TOOLS if use_tools else instructor.Mode.JSON
        return instructor.from_openai(raw_client, mode=mode)

    def _extract_prompt_text(self, event: Any) -> str:
        """Best-effort extraction of the original user prompt from the event."""
        try:
            agent = getattr(event, "agent", None)
            if agent is None:
                return ""
            messages = getattr(agent, "messages", []) or []
            for msg in messages:
                if msg.get("role") == "user":
                    content = msg.get("content", [])
                    if isinstance(content, str):
                        return content
                    for c in content:
                        if isinstance(c, dict) and "text" in c:
                            return c["text"]
            return ""
        except Exception:
            return ""

    @staticmethod
    def _is_placeholder(text: str) -> bool:
        """Return True if text is a known placeholder/error stub worth discarding."""
        if not text or not text.strip():
            return True
        return any(p.match(text) for p in _PLACEHOLDER_TEXT_PATTERNS)

    def _on_after(self, event: Any) -> None:
        """Post-process final response — run instructor, inject structured output."""
        try:
            agent = getattr(event, "agent", None)
            if agent is None:
                return
            messages = getattr(agent, "messages", []) or []
            if not messages:
                return

            last = messages[-1]
            if last.get("role") != "assistant":
                return

            content = last.get("content", [])
            raw_text_parts: list[str] = []
            if isinstance(content, str):
                raw_text_parts.append(content)
            else:
                for c in content:
                    if isinstance(c, dict) and "text" in c:
                        raw_text_parts.append(c["text"])

            # Separate real text from placeholder/error stubs.
            real_text_parts = [t for t in raw_text_parts if not self._is_placeholder(t)]
            model_output_text = "\n".join(raw_text_parts).strip()
            clean_output_text = "\n".join(real_text_parts).strip()
            original_prompt = self._extract_prompt_text(event)

            # Compose a focused prompt. Prefer the cleaned text (without the
            # stub) so instructor doesn't try to "interpret" [Error 400].
            instructor_input = clean_output_text or model_output_text or "(no text — infer from context)"
            enforcement_prompt = (
                f"Original request:\n{original_prompt}\n\n"
                f"Agent response (to extract structured data from):\n"
                f"{instructor_input}\n\n"
                f"Return a validated {self.schema.__name__} object."
            )

            validated = None
            mode_used = None
            last_err: Exception | None = None
            for use_tools in (True, False):
                try:
                    client = self._build_client(use_tools=use_tools)
                    validated = client.chat.completions.create(
                        model=self.model_id,
                        response_model=self.schema,
                        max_retries=self.max_retries,
                        messages=[{"role": "user", "content": enforcement_prompt}],
                    )
                    mode_used = "TOOLS" if use_tools else "JSON"
                    break
                except Exception as inner_err:
                    last_err = inner_err
                    logger.warning(
                        "StructuredOutputEnforcer mode=%s failed for %s: %s",
                        "TOOLS" if use_tools else "JSON",
                        self.schema.__name__, inner_err,
                    )
            if validated is None:
                # Both modes failed — give up cleanly, no synthetic toolUse,
                # caller keeps the raw markdown response.
                raise last_err if last_err else RuntimeError(
                    "StructuredOutputEnforcer: instructor returned no validated object"
                )

            synthetic = {
                "toolUse": {
                    "toolUseId": f"enforced_{self.schema.__name__.lower()}",
                    "name": self.schema.__name__,
                    "input": validated.model_dump(),
                }
            }

            # Rebuild the assistant content: drop placeholder text, keep
            # non-text blocks (toolUse results the model already produced,
            # reasoning blocks, etc.), append the synthetic enforcement block.
            new_content: list[Any] = []
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and "text" in c:
                        if not self._is_placeholder(c["text"]):
                            new_content.append(c)
                    else:
                        new_content.append(c)
                new_content.append(synthetic)
            else:
                # content was a string — replace with our structured pair,
                # preserving any real text.
                if clean_output_text:
                    new_content.append({"text": clean_output_text})
                new_content.append(synthetic)

            last["content"] = new_content

            logger.info(
                "StructuredOutputEnforcer injected %s mode=%s (dropped_placeholder=%s)",
                self.schema.__name__, mode_used,
                len(raw_text_parts) != len(real_text_parts),
            )
        except Exception as e:
            logger.exception(
                "StructuredOutputEnforcer failed to enforce schema: %s", e
            )
            # Do not raise — we prefer a response with free-form output over
            # crashing the entire agent invocation
