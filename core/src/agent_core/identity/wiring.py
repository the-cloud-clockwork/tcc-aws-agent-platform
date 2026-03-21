"""Bridge between blueprint identity config and runtime decorators.

``IdentityWiring`` reads ``CredentialConfig`` entries from the blueprint
and provides decorator factories so domain tool functions get the correct
tokens injected at runtime.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from agent_core.identity.cache import CredentialCache
from agent_core.identity.decorators import requires_access_token, requires_api_key
from agent_core.schemas.identity_config import CredentialConfig, CredentialType

logger = logging.getLogger(__name__)


class IdentityWiring:
    """Wire identity configuration from blueprint into agent tools.

    Created once per ``build_agent_session()`` call with a session-scoped
    ``CredentialCache``.

    Usage in domain code::

        with loader.build_agent_session("my-agent") as session:
            # Get a decorator for a named credential
            dec = session.identity.get_api_key_decorator("external-api")

            @tool
            def call_external(query: str) -> str:
                @dec
                def _inner(*, api_key: str) -> str:
                    return requests.get(url, headers={"X-API-Key": api_key}).text
                return _inner()
    """

    def __init__(
        self,
        credentials: list[CredentialConfig],
        cache: CredentialCache | None = None,
    ) -> None:
        self._credentials = {c.name: c for c in credentials}
        self._cache = cache or CredentialCache()

    def get_api_key_decorator(self, credential_name: str) -> Callable[..., Any]:
        """Get a ``@requires_api_key`` decorator for the named credential.

        Raises:
            ValueError: If credential not declared or not of type ``api_key``.
        """
        config = self._get_config(credential_name, CredentialType.API_KEY)
        return requires_api_key(provider_name=config.provider)

    def get_access_token_decorator(self, credential_name: str) -> Callable[..., Any]:
        """Get a ``@requires_access_token`` decorator for the named credential.

        Resolves ``callback_url`` from the env var declared in config.

        Raises:
            ValueError: If credential not declared or not of type ``oauth2``.
        """
        config = self._get_config(credential_name, CredentialType.OAUTH2)

        callback_url = None
        if config.callback_url_env:
            callback_url = os.environ.get(config.callback_url_env)

        return requires_access_token(
            provider_name=config.provider,
            scopes=config.scopes or None,
            auth_flow=config.auth_flow.value if config.auth_flow else "M2M",
            on_auth_url=self.default_on_auth_url,
            callback_url=callback_url,
        )

    def get_credential_map(self) -> dict[str, CredentialConfig]:
        """Return name → CredentialConfig mapping for runtime lookup."""
        return dict(self._credentials)

    @staticmethod
    def default_on_auth_url(url: str) -> None:
        """Default 3LO callback — logs the authorization URL."""
        logger.warning("User authorization required. Visit: %s", url)

    def _get_config(
        self, credential_name: str, expected_type: CredentialType
    ) -> CredentialConfig:
        config = self._credentials.get(credential_name)
        if config is None:
            raise ValueError(
                f"Credential '{credential_name}' not declared in blueprint. "
                f"Available: {list(self._credentials.keys())}"
            )
        if config.type != expected_type:
            raise ValueError(
                f"Credential '{credential_name}' is type '{config.type.value}', "
                f"expected '{expected_type.value}'."
            )
        return config
