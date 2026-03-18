"""AgentCore Identity -- credential provider abstraction and registry."""

from agent_core.identity.providers import (
    Credential,
    CredentialError,
    IdentityProvider,
    ProviderRegistry,
)

__all__ = ["Credential", "CredentialError", "IdentityProvider", "ProviderRegistry"]
