"""Cognito-backed identity provider."""
from __future__ import annotations

from typing import TYPE_CHECKING

from agent_core.identity.providers import Credential, IdentityProvider

if TYPE_CHECKING:
    from agent_core.identity.cache import CredentialCache


class CognitoProvider(IdentityProvider):
    """Resolve credentials via AgentCore Identity for Cognito user pools.

    Supports both ``USER_FEDERATION`` (3LO) and ``M2M`` (client credentials)
    auth flows.  The actual OAuth state machine is managed by AgentCore
    Identity — this provider is a resolution wrapper.
    """

    def __init__(
        self,
        provider_name: str = "cognito",
        *,
        credential_id: str | None = None,
        cache: CredentialCache | None = None,
    ) -> None:
        super().__init__(
            provider_name=provider_name,
            credential_id=credential_id,
            cache=cache,
        )

    def get_credential(self) -> Credential:
        """Resolve credential (cache-first, then AgentCore Identity)."""
        return self._cached_get()

    def refresh_credential(self) -> Credential:
        """Force-refresh credential via AgentCore Identity."""
        return self._cached_refresh()
