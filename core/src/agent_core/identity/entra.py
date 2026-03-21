"""Microsoft Entra ID (Azure AD) identity provider."""
from __future__ import annotations

from typing import TYPE_CHECKING

from agent_core.identity.providers import Credential, IdentityProvider

if TYPE_CHECKING:
    from agent_core.identity.cache import CredentialCache


class EntraProvider(IdentityProvider):
    """Resolve credentials via AgentCore Identity for Entra ID integrations.

    Delegates to AgentCore Identity which manages the Entra OAuth2
    integration.  Provider name maps to the credential provider
    registered in AgentCore Identity.
    """

    def __init__(
        self,
        provider_name: str = "entra",
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
