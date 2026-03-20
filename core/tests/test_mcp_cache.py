"""Tests for the generic Redis caching layer."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

import agent_core.mcp.cache as cache_mod
from agent_core.mcp.cache import (
    _cache_key,
    _override_redis,
    cache_get,
    cache_set,
)


@pytest.fixture(autouse=True)
def _reset_redis_client():
    """Reset the module-level redis client between tests."""
    cache_mod._redis_client = None
    yield
    cache_mod._redis_client = None


class TestCacheKey:
    def test_deterministic(self):
        k1 = _cache_key("data", symbol="item-A", start="2025-01-06")
        k2 = _cache_key("data", symbol="item-A", start="2025-01-06")
        assert k1 == k2

    def test_different_params_different_key(self):
        k1 = _cache_key("data", symbol="item-A")
        k2 = _cache_key("data", symbol="item-B")
        assert k1 != k2

    def test_prefix_included(self):
        k = _cache_key("data", prefix="svc", symbol="item-A")
        assert k.startswith("svc:data:")

    def test_no_prefix(self):
        k = _cache_key("data", symbol="item-A")
        assert k.startswith("data:")
        assert k.count(":") == 2  # namespace:hash (no leading prefix:)

    def test_key_length(self):
        k = _cache_key("ns", prefix="p", x=1)
        parts = k.split(":")
        assert len(parts) == 3
        assert len(parts[2]) == 12  # sha256 truncated to 12


class TestCacheGetSet:
    def test_cache_get_returns_none_without_redis(self):
        assert cache_get("ns", symbol="X") is None

    def test_cache_set_noop_without_redis(self):
        cache_set("ns", {"a": 1}, symbol="X")  # should not raise

    def test_cache_get_hit(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({"bars": [1, 2, 3]})
        _override_redis(mock_redis)

        result = cache_get("data", prefix="svc", symbol="item-A")
        assert result == {"bars": [1, 2, 3]}

    def test_cache_get_miss(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        _override_redis(mock_redis)

        assert cache_get("data", prefix="svc", symbol="item-A") is None

    def test_cache_get_exception_returns_none(self):
        mock_redis = MagicMock()
        mock_redis.get.side_effect = ConnectionError("boom")
        _override_redis(mock_redis)

        assert cache_get("data", symbol="item-A") is None

    def test_cache_set_writes(self):
        mock_redis = MagicMock()
        _override_redis(mock_redis)

        cache_set("data", {"bars": [1]}, ttl_seconds=60, prefix="svc", symbol="item-A")
        mock_redis.setex.assert_called_once()

    def test_cache_set_exception_does_not_raise(self):
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = ConnectionError("boom")
        _override_redis(mock_redis)

        cache_set("ns", {"a": 1}, symbol="X")  # should not raise


class TestWithFakeRedis:
    @pytest.fixture
    def fake_redis(self):
        try:
            import fakeredis
        except ImportError:
            pytest.skip("fakeredis not installed")
        return fakeredis.FakeRedis(decode_responses=True)

    def test_roundtrip(self, fake_redis):
        _override_redis(fake_redis)

        cache_set("data", {"bars": [1, 2]}, ttl_seconds=60, prefix="svc", symbol="item-A")
        result = cache_get("data", prefix="svc", symbol="item-A")
        assert result == {"bars": [1, 2]}

    def test_miss(self, fake_redis):
        _override_redis(fake_redis)
        assert cache_get("data", prefix="svc", symbol="MISSING") is None

    def test_different_prefixes_isolated(self, fake_redis):
        _override_redis(fake_redis)

        cache_set("data", {"v": 1}, prefix="svc", symbol="item-A")
        cache_set("data", {"v": 2}, prefix="other", symbol="item-A")

        assert cache_get("data", prefix="svc", symbol="item-A") == {"v": 1}
        assert cache_get("data", prefix="other", symbol="item-A") == {"v": 2}
