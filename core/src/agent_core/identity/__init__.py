"""AgentCore Identity -- credential providers, decorators, and wiring."""

from agent_core.identity.cache import CredentialCache
from agent_core.identity.client import IdentityClient
from agent_core.identity.cognito import CognitoProvider
from agent_core.identity.entra import EntraProvider
from agent_core.identity.okta import OktaProvider
from agent_core.identity.providers import (
    Credential,
    CredentialError,
    IdentityProvider,
    ProviderRegistry,
)
from agent_core.identity.wiring import IdentityWiring

__all__ = [
    "CognitoProvider",
    "Credential",
    "CredentialCache",
    "CredentialError",
    "EntraProvider",
    "IdentityClient",
    "IdentityProvider",
    "IdentityWiring",
    "OktaProvider",
    "ProviderRegistry",
]
