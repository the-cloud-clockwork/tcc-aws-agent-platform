"""Platform wrapper for AgentCore Identity service CRUD operations."""
from __future__ import annotations

import logging
import os
from typing import Any

from bedrock_agentcore.services.identity import IdentityClient as SdkIdentityClient

from agent_core.identity.providers import CredentialError

logger = logging.getLogger(__name__)


class IdentityClient:
    """Manage credential providers in AgentCore Identity.

    Wraps ``bedrock_agentcore.services.identity.IdentityClient`` with
    structured logging and error mapping to ``CredentialError``.
    """

    def __init__(self, region: str | None = None) -> None:
        self._region = region or os.environ.get("AWS_REGION", "eu-west-1")
        try:
            self._client = SdkIdentityClient(region=self._region)
        except Exception as exc:
            raise CredentialError(
                f"Failed to initialise AgentCore IdentityClient in {self._region}: {exc}"
            ) from exc
        logger.info("IdentityClient initialised in %s", self._region)

    def create_api_key_provider(
        self,
        name: str,
        secret_name: str,
    ) -> dict[str, Any]:
        """Create an API key credential provider backed by Secrets Manager.

        Args:
            name: Provider name (referenced by ``@requires_api_key``).
            secret_name: Secrets Manager secret name holding the API key.

        Returns:
            Provider creation response from AgentCore Identity.
        """
        try:
            result = self._client.create_api_key_credential_provider(
                {"name": name, "secret_name": secret_name}
            )
            logger.info("Created API key provider: %s", name)
            return result
        except Exception as exc:
            raise CredentialError(
                f"Failed to create API key provider '{name}': {exc}"
            ) from exc

    def create_oauth2_provider(
        self,
        name: str,
        *,
        client_id: str,
        client_secret: str,
        authorization_url: str,
        token_url: str,
        scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create an OAuth2 credential provider.

        Args:
            name: Provider name (referenced by ``@requires_access_token``).
            client_id: OAuth2 client ID.
            client_secret: OAuth2 client secret.
            authorization_url: Authorization endpoint URL.
            token_url: Token endpoint URL.
            scopes: Default OAuth2 scopes.

        Returns:
            Provider creation response from AgentCore Identity.
        """
        config: dict[str, Any] = {
            "name": name,
            "client_id": client_id,
            "client_secret": client_secret,
            "authorization_url": authorization_url,
            "token_url": token_url,
        }
        if scopes:
            config["scopes"] = scopes
        try:
            result = self._client.create_oauth2_credential_provider(config)
            logger.info("Created OAuth2 provider: %s", name)
            return result
        except Exception as exc:
            raise CredentialError(
                f"Failed to create OAuth2 provider '{name}': {exc}"
            ) from exc

    def get_provider(self, name: str) -> dict[str, Any]:
        """Get credential provider details by name."""
        try:
            return self._client.get_credential_provider(name)
        except Exception as exc:
            raise CredentialError(
                f"Failed to get provider '{name}': {exc}"
            ) from exc

    def list_providers(self) -> list[dict[str, Any]]:
        """List all credential providers."""
        try:
            return self._client.list_credential_providers()
        except Exception as exc:
            raise CredentialError(
                f"Failed to list providers: {exc}"
            ) from exc

    def delete_provider(self, name: str) -> None:
        """Delete a credential provider."""
        try:
            self._client.delete_credential_provider(name)
            logger.info("Deleted provider: %s", name)
        except Exception as exc:
            raise CredentialError(
                f"Failed to delete provider '{name}': {exc}"
            ) from exc
