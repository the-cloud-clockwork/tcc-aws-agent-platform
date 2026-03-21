"""Platform wrappers for AgentCore Identity auth decorators.

Thin wrappers around ``bedrock_agentcore.identity.auth`` that add
structured logging and integrate with the platform's credential cache.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable

from bedrock_agentcore.identity.auth import (
    requires_access_token as _sdk_requires_access_token,
    requires_api_key as _sdk_requires_api_key,
)

logger = logging.getLogger(__name__)


def _default_on_auth_url(url: str) -> None:
    """Default 3LO callback — logs the authorization URL at WARNING level."""
    logger.warning("User authorization required. Visit: %s", url)


def requires_access_token(
    provider_name: str,
    scopes: list[str] | None = None,
    auth_flow: str = "M2M",
    on_auth_url: Callable[[str], None] | None = None,
    callback_url: str | None = None,
    into: str = "access_token",
    force_authentication: bool = False,
) -> Callable[..., Any]:
    """Decorator that injects an OAuth2 access token into the wrapped function.

    Delegates to ``bedrock_agentcore.identity.auth.requires_access_token``.
    Adds structured logging for audit and debugging.

    Args:
        provider_name: Name of credential provider registered in AgentCore Identity.
        scopes: OAuth2 scopes to request.
        auth_flow: ``"USER_FEDERATION"`` (3LO) or ``"M2M"``.
        on_auth_url: Callback invoked with the authorization URL (3LO only).
            Defaults to logging the URL at WARNING level.
        callback_url: OAuth2 redirect URL (3LO only).
        into: Parameter name to inject the token into.
        force_authentication: Force re-authentication even if a valid token exists.

    Returns:
        Decorator function.
    """
    effective_on_auth_url = on_auth_url or _default_on_auth_url

    sdk_decorator = _sdk_requires_access_token(
        provider_name=provider_name,
        scopes=scopes or [],
        auth_flow=auth_flow,
        on_auth_url=effective_on_auth_url,
        callback_url=callback_url,
        into=into,
        force_authentication=force_authentication,
    )

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        wrapped = sdk_decorator(fn)

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.debug(
                "Resolving access token: provider=%s flow=%s scopes=%s",
                provider_name,
                auth_flow,
                scopes,
            )
            return await wrapped(*args, **kwargs)

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.debug(
                "Resolving access token: provider=%s flow=%s scopes=%s",
                provider_name,
                auth_flow,
                scopes,
            )
            return wrapped(*args, **kwargs)

        import asyncio

        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    return decorator


def requires_api_key(
    provider_name: str,
    into: str = "api_key",
) -> Callable[..., Any]:
    """Decorator that injects an API key from Secrets Manager into the wrapped function.

    Delegates to ``bedrock_agentcore.identity.auth.requires_api_key``.
    Adds structured logging for audit and debugging.

    Args:
        provider_name: Name of API key credential provider.
        into: Parameter name to inject the key into.

    Returns:
        Decorator function.
    """
    sdk_decorator = _sdk_requires_api_key(
        provider_name=provider_name,
        into=into,
    )

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        wrapped = sdk_decorator(fn)

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.debug("Resolving API key: provider=%s", provider_name)
            return await wrapped(*args, **kwargs)

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.debug("Resolving API key: provider=%s", provider_name)
            return wrapped(*args, **kwargs)

        import asyncio

        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    return decorator
