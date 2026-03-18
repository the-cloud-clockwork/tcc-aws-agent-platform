"""Unit tests for AgentCore Memory manager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_core.memory.manager import MemoryManager, _InMemoryFallback, get_memory_manager


class TestInMemoryFallback:
    """Tests for the in-memory fallback when AgentCore Memory is unavailable."""

    def test_store_and_retrieve(self):
        fallback = _InMemoryFallback()
        fallback.update("key1", {"a": 1})
        assert fallback.get("key1") == {"a": 1}

    def test_update_merges(self):
        fallback = _InMemoryFallback()
        fallback.update("key1", {"a": 1})
        fallback.update("key1", {"b": 2})
        assert fallback.get("key1") == {"a": 1, "b": 2}

    def test_get_missing_returns_none(self):
        fallback = _InMemoryFallback()
        assert fallback.get("missing") is None

    def test_store_episodic(self):
        fallback = _InMemoryFallback()
        entry_id = fallback.store_episodic(content="AAPL gapped 5%")
        assert entry_id is not None

    def test_search_episodic(self):
        fallback = _InMemoryFallback()
        fallback.store_episodic(content="AAPL gapped 5% on Monday")
        fallback.store_episodic(content="TSLA earnings beat")

        results = fallback.search_episodic(query="AAPL gap")
        assert len(results["entries"]) == 1


class TestMemoryManager:
    """Tests for MemoryManager with fallback."""

    def test_get_session_memory(self):
        manager = MemoryManager()
        # Should use fallback since bedrock_agentcore not installed
        manager.update_session_memory(
            session_id="s123",
            agent_id="gap-detector",
            updates={"gap_count": 5},
        )
        result = manager.get_session_memory("s123")
        assert result is not None
        assert result.get("gap_count") == 5

    def test_semantic_search_fallback(self):
        manager = MemoryManager()
        manager.store_episodic(
            session_id="s123",
            agent_id="gap-detector",
            content="Found 3 gaps in AAPL, TSLA, NVDA",
        )
        results = manager.semantic_search(query="AAPL gaps")
        assert "entries" in results
