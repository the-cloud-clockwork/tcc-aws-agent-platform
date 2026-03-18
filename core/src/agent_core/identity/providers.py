"""AgentCore Identity credential providers.

Manages credential resolution for external services.
In AgentCore mode, Identity handles token refresh automatically.
In Lambda mode, tokens are managed via environment variables.

Provides the abstract IdentityProvider base class and a ProviderRegistry
for registering and looking up concrete providers at runtime.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Credential:
    """A resolved credential from AgentCore Identity or environment.

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


class IdentityProvider(ABC):
    """Base class for identity providers.

    Provides a uniform interface for credential resolution.
    In Lambda mode: reads from environment variables.
    In AgentCore mode: uses AgentCore Identity service.
    """

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name
        self.runtime_mode = os.environ.get("RUNTIME_MODE", "lambda")

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

    def _get_from_agentcore(self, credential_id: str) -> Credential:
        """Resolve credential via AgentCore Identity service.

        Args:
            credential_id: AgentCore credential reference ID.

        Returns:
            Resolved Credential.
        """
        try:
            from bedrock_agentcore.identity import AgentCoreIdentityClient

            client = AgentCoreIdentityClient(
                region=os.environ.get("AWS_REGION", "eu-west-1"),
            )
            token = client.get_credential(credential_id)

            return Credential(
                provider=self.provider_name,
                token_type=token.get("token_type", "bearer"),
                access_token=token["access_token"],
                expires_at=token.get("expires_at"),
                scopes=token.get("scopes"),
            )
        except ImportError:
            raise CredentialError(
                f"bedrock-agentcore-identity not installed for provider {self.provider_name}"
            )
        except KeyError as e:
            raise CredentialError(
                f"AgentCore Identity returned incomplete credential: {e}"
            )


class CredentialError(Exception):
    """Error resolving a credential."""

    pass


class ProviderRegistry:
    """Registry for identity providers.

    Allows registering provider classes by name and looking them up at runtime.

    Usage:
        registry = ProviderRegistry()
        registry.register("my_service", MyServiceProvider)
        provider = registry.get("my_service")
        cred = provider.get_credential()
    """

    def __init__(self) -> None:
        self._providers: dict[str, type[IdentityProvider]] = {}

    def register(self, name: str, provider_cls: type[IdentityProvider]) -> None:
        """Register a provider class by name.

        Args:
            name: Provider name (e.g., "external", "telegram").
            provider_cls: IdentityProvider subclass.
        """
        self._providers[name] = provider_cls
        logger.info("Registered identity provider: %s", name)

    def get(self, name: str) -> IdentityProvider:
        """Get a provider instance by name.

        Args:
            name: Registered provider name.

        Returns:
            IdentityProvider instance.

        Raises:
            ValueError: If provider name is not registered.
        """
        provider_cls = self._providers.get(name)
        if provider_cls is None:
            raise ValueError(
                f"Unknown provider: {name}. "
                f"Registered providers: {list(self._providers.keys())}"
            )
        return provider_cls()

    @property
    def registered_names(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())
