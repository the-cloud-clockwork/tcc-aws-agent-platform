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

See also: ``operator/inference-migration.md`` Stage 2.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


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

    def _build_client(self) -> Any:
        """Lazily construct an instructor-wrapped OpenAI client."""
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
        # Mode.JSON works on any OpenAI-compatible endpoint without requiring
        # provider-native response_format enforcement
        return instructor.from_openai(raw_client, mode=instructor.Mode.JSON)

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
            text_parts: list[str] = []
            if isinstance(content, str):
                text_parts.append(content)
            else:
                for c in content:
                    if isinstance(c, dict) and "text" in c:
                        text_parts.append(c["text"])

            model_output_text = "\n".join(text_parts).strip()
            original_prompt = self._extract_prompt_text(event)

            # Compose a focused prompt: original request + the agent's final text
            # plus an instruction to format according to the schema
            enforcement_prompt = (
                f"Original request:\n{original_prompt}\n\n"
                f"Agent response (to extract structured data from):\n"
                f"{model_output_text or '(no text — infer from context)'}\n\n"
                f"Return a validated {self.schema.__name__} object."
            )

            client = self._build_client()
            validated = client.chat.completions.create(
                model=self.model_id,
                response_model=self.schema,
                max_retries=self.max_retries,
                messages=[{"role": "user", "content": enforcement_prompt}],
            )

            # Inject as synthetic toolUse block (matches Bedrock structured output shape)
            synthetic = {
                "toolUse": {
                    "toolUseId": f"enforced_{self.schema.__name__.lower()}",
                    "name": self.schema.__name__,
                    "input": validated.model_dump(),
                }
            }
            if isinstance(content, list):
                content.append(synthetic)
            else:
                last["content"] = [{"text": content}, synthetic]

            logger.info(
                "StructuredOutputEnforcer injected %s into agent output",
                self.schema.__name__,
            )
        except Exception as e:
            logger.exception(
                "StructuredOutputEnforcer failed to enforce schema: %s", e
            )
            # Do not raise — we prefer a response with free-form output over
            # crashing the entire agent invocation
