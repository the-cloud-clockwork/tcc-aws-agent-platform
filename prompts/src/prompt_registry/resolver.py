"""Version resolution logic for prompt references."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from prompt_registry.models import (
    DRAFT_ALLOWED_MODES,
    Mode,
    PromptResolveResponse,
    PromptStatus,
)
from prompt_registry.registry import PromptRegistry
from prompt_registry.storage import PromptStorage


@dataclass
class ParsedRef:
    """Result of parsing a prompt reference string."""

    prompt_id: str
    version: Optional[str] = None


def parse_prompt_ref(ref: str) -> ParsedRef:
    """
    Parse a prompt reference into prompt_id and optional version.

    Supported formats:
        gap_detector            -> (prompt_id="gap_detector", version=None)
        gap_detector_v1.2       -> (prompt_id="gap_detector", version="1.2")
        gap_detector_v1.2.0     -> (prompt_id="gap_detector", version="1.2.0")
        summarizer@2.0.0 -> (prompt_id="summarizer", version="2.0.0")
    """
    # Format: name@version
    if "@" in ref:
        parts = ref.split("@", 1)
        return ParsedRef(prompt_id=parts[0], version=parts[1])

    # Format: name_vX.Y or name_vX.Y.Z
    match = re.match(r"^(.+?)_v(\d+(?:\.\d+)*)$", ref)
    if match:
        return ParsedRef(prompt_id=match.group(1), version=match.group(2))

    # No version specified — resolve to latest stable
    return ParsedRef(prompt_id=ref, version=None)


class PromptResolver:
    """Resolves prompt references to actual prompt text."""

    def __init__(
        self,
        registry: PromptRegistry,
        storage: PromptStorage,
    ) -> None:
        self.registry = registry
        self.storage = storage

    def resolve(
        self,
        ref: str,
        mode: Mode = Mode.PRODUCTION,
    ) -> Optional[PromptResolveResponse]:
        """
        Resolve a prompt reference to its text content.

        In staging/production mode: only stable prompts are returned.
        In simulation/dev mode: draft prompts are also allowed.
        """
        parsed = parse_prompt_ref(ref)

        if parsed.version:
            return self._resolve_pinned(parsed, mode)
        return self._resolve_latest(parsed, mode)

    def _resolve_pinned(
        self, parsed: ParsedRef, mode: Mode
    ) -> Optional[PromptResolveResponse]:
        """Resolve a pinned version reference."""
        assert parsed.version is not None

        # Try exact match first
        prompt = self.registry.get_version(parsed.prompt_id, parsed.version)

        # If not found, try with .0 suffix (e.g., "1.2" -> "1.2.0")
        if prompt is None and parsed.version.count(".") < 2:
            padded = parsed.version + ".0" * (2 - parsed.version.count("."))
            prompt = self.registry.get_version(parsed.prompt_id, padded)

        if prompt is None:
            return None

        # Enforce mode-based access
        if prompt.status == PromptStatus.DRAFT and mode not in DRAFT_ALLOWED_MODES:
            return None

        if prompt.status == PromptStatus.DEPRECATED:
            return None

        text = self.storage.get(parsed.prompt_id, prompt.version)
        return PromptResolveResponse(
            prompt_id=prompt.prompt_id,
            version=prompt.version,
            text=text,
            status=prompt.status,
        )

    def _resolve_latest(
        self, parsed: ParsedRef, mode: Mode
    ) -> Optional[PromptResolveResponse]:
        """Resolve to the latest version based on mode."""
        # Always try stable first
        prompt = self.registry.get_latest_stable(parsed.prompt_id)

        # In draft-allowed modes, fall back to draft if no stable
        if prompt is None and mode in DRAFT_ALLOWED_MODES:
            prompt = self.registry.get_latest_draft(parsed.prompt_id)

        if prompt is None:
            return None

        text = self.storage.get(parsed.prompt_id, prompt.version)
        return PromptResolveResponse(
            prompt_id=prompt.prompt_id,
            version=prompt.version,
            text=text,
            status=prompt.status,
        )
