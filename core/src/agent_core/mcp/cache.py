"""Redis caching layer for MCP servers.

Provides cache_get/cache_set with lazy Redis init, graceful degradation
when Redis is unavailable, and configurable key prefixes.

Extracted from market-data-mcp — generalised for any MCP server.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_redis_client: Any = None


def _get_redis() -> Any:
    """Lazy-init Redis client. Returns None if Redis is unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis

        _redis_client = redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        logger.info("Redis cache connected at %s", redis_url)
        return _redis_client
    except Exception:
        logger.warning("Redis unavailable at %s — caching disabled", redis_url)
        _redis_client = None
        return None


def _override_redis(client: Any) -> None:
    """Override the Redis client (for testing with fakeredis)."""
    global _redis_client
    _redis_client = client


def _cache_key(namespace: str, *, prefix: str = "", **kwargs: Any) -> str:
    """Build a deterministic cache key.

    Format: ``{prefix}:{namespace}:{sha256_12chars}``
    """
    raw = json.dumps(kwargs, sort_keys=True, default=str)
    h = hashlib.sha256(raw.encode()).hexdigest()[:12]
    if prefix:
        return f"{prefix}:{namespace}:{h}"
    return f"{namespace}:{h}"


def cache_get(namespace: str, *, prefix: str = "", **kwargs: Any) -> Any | None:
    """Get a value from cache. Returns None on miss or if Redis unavailable."""
    r = _get_redis()
    if r is None:
        return None
    key = _cache_key(namespace, prefix=prefix, **kwargs)
    try:
        val = r.get(key)
        if val is not None:
            return json.loads(val)
    except Exception:
        logger.debug("Cache get failed for %s", key)
    return None


def cache_set(
    namespace: str,
    value: Any,
    ttl_seconds: int = 300,
    *,
    prefix: str = "",
    **kwargs: Any,
) -> None:
    """Set a value in cache with TTL."""
    r = _get_redis()
    if r is None:
        return
    key = _cache_key(namespace, prefix=prefix, **kwargs)
    try:
        r.setex(key, ttl_seconds, json.dumps(value, default=str))
    except Exception:
        logger.debug("Cache set failed for %s", key)
