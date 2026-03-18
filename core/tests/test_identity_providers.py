"""Unit tests for identity providers."""

from __future__ import annotations

import pytest

from agent_core.identity.providers import (
    Credential,
    IdentityProvider,
    ProviderRegistry,
)


class MockProvider(IdentityProvider):
    """Test identity provider."""

    def __init__(self) -> None:
        super().__init__("mock")

    def get_credential(self) -> Credential:
        return Credential(
            provider="mock",
            token_type="api_key",
            access_token="test-token-123",
        )

    def refresh_credential(self) -> Credential:
        return self.get_credential()


class TestIdentityProvider:
    """Tests for the abstract IdentityProvider."""

    def test_get_credential(self):
        provider = MockProvider()
        cred = provider.get_credential()
        assert cred.provider == "mock"
        assert cred.token_type == "api_key"
        assert cred.access_token == "test-token-123"

    def test_refresh_credential(self):
        provider = MockProvider()
        cred = provider.refresh_credential()
        assert cred.access_token == "test-token-123"


class TestProviderRegistry:
    """Tests for ProviderRegistry."""

    def test_register_and_get(self):
        registry = ProviderRegistry()
        registry.register("mock", MockProvider)
        provider = registry.get("mock")
        assert isinstance(provider, MockProvider)

    def test_get_unknown_raises(self):
        registry = ProviderRegistry()
        with pytest.raises(ValueError, match="Unknown provider"):
            registry.get("nonexistent")

    def test_registered_names(self):
        registry = ProviderRegistry()
        registry.register("a", MockProvider)
        registry.register("b", MockProvider)
        assert sorted(registry.registered_names) == ["a", "b"]
