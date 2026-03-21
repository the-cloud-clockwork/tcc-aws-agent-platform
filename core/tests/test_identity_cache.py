"""Tests for CredentialCache."""
from __future__ import annotations

import time

from agent_core.identity.cache import CredentialCache
from agent_core.identity.providers import Credential


def _make_credential(provider: str = "test", expires_at: str | None = None) -> Credential:
    return Credential(
        provider=provider,
        token_type="bearer",
        access_token="tok-123",
        expires_at=expires_at,
    )


class TestCredentialCache:
    def test_put_and_get(self) -> None:
        cache = CredentialCache()
        cred = _make_credential()
        cache.put("p1", cred)
        assert cache.get("p1") is cred

    def test_get_miss(self) -> None:
        cache = CredentialCache()
        assert cache.get("nonexistent") is None

    def test_cache_key_includes_auth_flow(self) -> None:
        cache = CredentialCache()
        cred_m2m = _make_credential("m2m")
        cred_3lo = _make_credential("3lo")
        cache.put("provider", cred_m2m, auth_flow="M2M")
        cache.put("provider", cred_3lo, auth_flow="USER_FEDERATION")
        assert cache.get("provider", "M2M") is cred_m2m
        assert cache.get("provider", "USER_FEDERATION") is cred_3lo

    def test_invalidate(self) -> None:
        cache = CredentialCache()
        cache.put("p1", _make_credential())
        cache.invalidate("p1")
        assert cache.get("p1") is None

    def test_clear(self) -> None:
        cache = CredentialCache()
        cache.put("p1", _make_credential())
        cache.put("p2", _make_credential())
        cache.clear()
        assert cache.get("p1") is None
        assert cache.get("p2") is None

    def test_ttl_expiry(self) -> None:
        cache = CredentialCache(ttl_seconds=1)
        cache.put("p1", _make_credential())
        assert cache.get("p1") is not None
        time.sleep(1.1)
        assert cache.get("p1") is None

    def test_ttl_from_expires_at(self) -> None:
        from datetime import datetime, timedelta, timezone

        # Credential expiring in 10 seconds — cache should use 80% = 8 seconds
        expires = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
        cache = CredentialCache(ttl_seconds=300)
        cred = _make_credential(expires_at=expires)
        cache.put("p1", cred)
        # Should still be cached (within 8 second window)
        assert cache.get("p1") is not None

    def test_invalid_expires_at_falls_back_to_default(self) -> None:
        cache = CredentialCache(ttl_seconds=300)
        cred = _make_credential(expires_at="not-a-date")
        cache.put("p1", cred)
        assert cache.get("p1") is not None
