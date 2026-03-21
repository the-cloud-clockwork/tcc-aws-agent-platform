"""In-memory credential cache with TTL-based expiration."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from agent_core.identity.providers import Credential

logger = logging.getLogger(__name__)


class CredentialCache:
    """Thread-safe in-memory cache for resolved credentials.

    Each credential is cached by ``(provider_name, auth_flow)`` key.
    Expired entries are evicted on access.  Session-scoped — create one
    per ``build_agent_session()`` call to prevent cross-session leakage.
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._default_ttl = ttl_seconds
        self._store: dict[tuple[str, str], tuple[Credential, float]] = {}
        self._lock = threading.Lock()

    def get(self, provider_name: str, auth_flow: str = "") -> Credential | None:
        """Return a cached credential if present and not expired."""
        key = (provider_name, auth_flow)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            credential, expires_at_ts = entry
            if time.monotonic() >= expires_at_ts:
                del self._store[key]
                logger.debug("Cache miss (expired): %s", key)
                return None
            logger.debug("Cache hit: %s", key)
            return credential

    def put(
        self,
        provider_name: str,
        credential: Credential,
        auth_flow: str = "",
    ) -> None:
        """Cache a credential with TTL derived from its expiry or the default."""
        key = (provider_name, auth_flow)
        ttl = self._resolve_ttl(credential)
        expires_at_ts = time.monotonic() + ttl
        with self._lock:
            self._store[key] = (credential, expires_at_ts)
        logger.debug("Cached credential: %s (ttl=%ds)", key, ttl)

    def invalidate(self, provider_name: str, auth_flow: str = "") -> None:
        """Remove a specific credential from cache."""
        key = (provider_name, auth_flow)
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Remove all cached credentials."""
        with self._lock:
            self._store.clear()

    def _resolve_ttl(self, credential: Credential) -> int:
        """Compute TTL from credential expiry or fall back to default."""
        if credential.expires_at is not None:
            try:
                expires_dt = datetime.fromisoformat(credential.expires_at)
                if expires_dt.tzinfo is None:
                    expires_dt = expires_dt.replace(tzinfo=timezone.utc)
                remaining = (expires_dt - datetime.now(timezone.utc)).total_seconds()
                if remaining > 0:
                    # Cache for 80% of remaining lifetime (safety margin)
                    return max(1, int(remaining * 0.8))
            except (ValueError, TypeError):
                pass
        return self._default_ttl
