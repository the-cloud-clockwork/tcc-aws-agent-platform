"""Tests for provider routing — mode resolution + provider instantiation."""

from __future__ import annotations

import pytest

from agent_core.execution.mode import ExecutionMode
from agent_core.mcp.provider_routing import resolve_provider


class FakeSimProvider:
    pass


class FakeLiveProvider:
    pass


class FakeStagingProvider:
    pass


REGISTRY = {
    ExecutionMode.SIMULATION: FakeSimProvider,
    ExecutionMode.STAGING: FakeStagingProvider,
    ExecutionMode.PRODUCTION: FakeLiveProvider,
}


class TestResolveProvider:
    def test_simulation_mode(self, monkeypatch):
        monkeypatch.setenv("EXECUTION_MODE", "simulation")
        provider = resolve_provider(REGISTRY)
        assert isinstance(provider, FakeSimProvider)

    def test_staging_mode(self, monkeypatch):
        monkeypatch.setenv("EXECUTION_MODE", "staging")
        provider = resolve_provider(REGISTRY)
        assert isinstance(provider, FakeStagingProvider)

    def test_production_mode(self, monkeypatch):
        monkeypatch.setenv("EXECUTION_MODE", "production")
        provider = resolve_provider(REGISTRY)
        assert isinstance(provider, FakeLiveProvider)

    def test_alias_to_simulation(self, monkeypatch):
        monkeypatch.setenv("EXECUTION_MODE", "dev")
        provider = resolve_provider(REGISTRY, aliases={"dev": "simulation"})
        assert isinstance(provider, FakeSimProvider)

    def test_alias_to_staging(self, monkeypatch):
        monkeypatch.setenv("EXECUTION_MODE", "preview")
        provider = resolve_provider(REGISTRY, aliases={"preview": "staging"})
        assert isinstance(provider, FakeStagingProvider)

    def test_alias_to_production(self, monkeypatch):
        monkeypatch.setenv("EXECUTION_MODE", "release")
        provider = resolve_provider(REGISTRY, aliases={"release": "production"})
        assert isinstance(provider, FakeLiveProvider)

    def test_custom_alias(self, monkeypatch):
        monkeypatch.setenv("EXECUTION_MODE", "test_mode")
        provider = resolve_provider(
            REGISTRY,
            aliases={"test_mode": "simulation"},
        )
        assert isinstance(provider, FakeSimProvider)

    def test_missing_mode_raises(self, monkeypatch):
        monkeypatch.setenv("EXECUTION_MODE", "production")
        partial_registry = {ExecutionMode.SIMULATION: FakeSimProvider}
        with pytest.raises(ValueError, match="No provider registered"):
            resolve_provider(partial_registry)

    def test_default_is_simulation(self, monkeypatch):
        monkeypatch.delenv("EXECUTION_MODE", raising=False)
        provider = resolve_provider(REGISTRY)
        assert isinstance(provider, FakeSimProvider)
