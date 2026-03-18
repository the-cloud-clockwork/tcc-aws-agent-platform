"""Tests for PromptRegistryClient."""
from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from agent_core.prompt.client import PromptRegistryClient, PromptResolutionError

if TYPE_CHECKING:
    from pathlib import Path


class TestPromptRegistryClient:
    @respx.mock
    def test_fetch_remote_success(self) -> None:
        respx.get("http://test-registry/prompts/gap_detector_v1.2").mock(
            return_value=httpx.Response(
                200,
                json={"text": "You are a gap detection agent."},
            )
        )
        client = PromptRegistryClient(registry_url="http://test-registry")
        result = client.get("gap_detector_v1.2")
        assert result == "You are a gap detection agent."

    @respx.mock
    def test_fetch_remote_prompt_text_key(self) -> None:
        respx.get("http://test-registry/prompts/test_v1").mock(
            return_value=httpx.Response(
                200,
                json={"prompt_text": "Hello from registry."},
            )
        )
        client = PromptRegistryClient(registry_url="http://test-registry")
        assert client.get("test_v1") == "Hello from registry."

    def test_fallback_to_local(self, tmp_prompts: Path) -> None:
        # Use an unreachable URL so remote fails.
        client = PromptRegistryClient(
            registry_url="http://unreachable-host:9999",
            local_dir=tmp_prompts,
            timeout=0.5,
        )
        result = client.get("gap_detector_v1.2")
        assert "gap detection agent" in result

    def test_local_latest(self, tmp_prompts: Path) -> None:
        client = PromptRegistryClient(
            registry_url="http://unreachable-host:9999",
            local_dir=tmp_prompts,
            timeout=0.5,
        )
        result = client.get("gap_detector")
        assert "(latest)" in result

    def test_no_local_dir_raises(self) -> None:
        client = PromptRegistryClient(
            registry_url="http://unreachable-host:9999",
            timeout=0.5,
        )
        with pytest.raises(PromptResolutionError, match="No local_dir"):
            client.get("missing_prompt")

    def test_missing_local_file_raises(self, tmp_prompts: Path) -> None:
        client = PromptRegistryClient(
            registry_url="http://unreachable-host:9999",
            local_dir=tmp_prompts,
            timeout=0.5,
        )
        with pytest.raises(PromptResolutionError, match="not found"):
            client.get("totally_missing_ref")

    @respx.mock
    def test_empty_response_falls_back(self, tmp_prompts: Path) -> None:
        respx.get("http://test-registry/prompts/gap_detector_v1.2").mock(
            return_value=httpx.Response(200, json={})
        )
        client = PromptRegistryClient(
            registry_url="http://test-registry",
            local_dir=tmp_prompts,
        )
        result = client.get("gap_detector_v1.2")
        assert "gap detection agent" in result
