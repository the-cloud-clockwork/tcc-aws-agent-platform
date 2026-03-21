"""AgentCore Identity credential providers.

Manages credential resolution for external services via AgentCore Identity.
All credential resolution flows through the AgentCore Identity service —
there is no Lambda/env-var fallback.

Provides the abstract ``IdentityProvider`` base class and a ``ProviderRegistry``
for registering and looking up concrete providers at runtime.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_core.identity.cache import CredentialCache

logger = logging.getLogger(__name__)


@dataclass
class Credential:
    """A resolved credential from AgentCore Identity.

    Attributes:
        provider: Provider name string.
        token_type: Token type (bearer, api_key, etc.).
        access_token: The actual token value (resolved at runtime).
        expires_at: ISO timestamp when the token expires (if applicable).
        scopes: OAuth scopes granted (if applicable).
    """

    provider: str
    token_type: str
    access_token: str
    expires_at: str | None = None
    scopes: list[str] | None = None


class CredentialError(Exception):
    """Error resolving a credential."""


class IdentityProvider(ABC):
    """Base class for identity providers.

    All credential resolution goes through AgentCore Identity service.
    Subclasses implement ``get_credential`` and ``refresh_credential``
    using ``_get_from_agentcore`` as the underlying resolution mechanism.
    """

    def __init__(
        self,
        provider_name: str,
        *,
        credential_id: str | None = None,
        cache: CredentialCache | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.credential_id = credential_id or provider_name
        self._cache = cache

    @abstractmethod
    def get_credential(self) -> Credential:
        """Resolve a credential for this provider.

        Returns:
            Credential with access token.

        Raises:
            CredentialError: If credential cannot be resolved.
        """
        ...

    @abstractmethod
    def refresh_credential(self) -> Credential:
        """Force-refresh the credential (e.g., OAuth token refresh).

        Returns:
            Fresh Credential.
        """
        ...

    def _get_from_agentcore(self, credential_id: str | None = None) -> Credential:
        """Resolve credential via AgentCore Identity service.

        Args:
            credential_id: AgentCore credential reference ID.
                Falls back to ``self.credential_id``.

        Returns:
            Resolved Credential.

        Raises:
            CredentialError: On SDK import failure or missing fields.
        """
        cred_id = credential_id or self.credential_id
        from bedrock_agentcore.identity import AgentCoreIdentityClient

        region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION")
        if not region:
            raise CredentialError(
                "No AWS region configured.  Export AWS_DEFAULT_REGION."
            )

        try:
            client = AgentCoreIdentityClient(region=region)
            token: dict[str, Any] = client.get_credential(cred_id)
        except Exception as exc:
            raise CredentialError(
                f"AgentCore Identity resolution failed for '{cred_id}': {exc}"
            ) from exc

        try:
            return Credential(
                provider=self.provider_name,
                token_type=token.get("token_type", "bearer"),
                access_token=token["access_token"],
                expires_at=token.get("expires_at"),
                scopes=token.get("scopes"),
            )
        except KeyError as exc:
            raise CredentialError(
                f"AgentCore Identity returned incomplete credential: {exc}"
            ) from exc

    def _cached_get(self, auth_flow: str = "") -> Credential:
        """Resolve credential with cache-first strategy."""
        if self._cache is not None:
            cached = self._cache.get(self.provider_name, auth_flow)
            if cached is not None:
                return cached

        credential = self._get_from_agentcore()

        if self._cache is not None:
            self._cache.put(self.provider_name, credential, auth_flow)

        return credential

    def _cached_refresh(self, auth_flow: str = "") -> Credential:
        """Force-refresh: invalidate cache, then resolve fresh."""
        if self._cache is not None:
            self._cache.invalidate(self.provider_name, auth_flow)
        credential = self._get_from_agentcore()
        if self._cache is not None:
            self._cache.put(self.provider_name, credential, auth_flow)
        return credential


class ProviderRegistry:
    """Registry for identity providers.

    Usage::

        registry = ProviderRegistry()
        registry.register("my_service", MyServiceProvider)
        provider = registry.get("my_service")
        cred = provider.get_credential()
    """

    def __init__(self) -> None:
        self._providers: dict[str, type[IdentityProvider]] = {}

    def register(self, name: str, provider_cls: type[IdentityProvider]) -> None:
        """Register a provider class by name."""
        self._providers[name] = provider_cls
        logger.info("Registered identity provider: %s", name)

    def get(self, name: str) -> IdentityProvider:
        """Get a provider instance by name.

        Raises:
            ValueError: If provider name is not registered.
        """
        provider_cls = self._providers.get(name)
        if provider_cls is None:
            raise ValueError(
                f"Unknown provider: {name}. Registered: {list(self._providers.keys())}"
            )
        return provider_cls(provider_name=name)

    @property
    def registered_names(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())
