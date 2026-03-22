---
title: Identity
nav_order: 3
---

# Identity

The Identity subsystem manages all authentication and credential flows for agents. It handles both inbound auth (verifying callers) and outbound auth (acquiring credentials to call external systems), with an in-process credential cache to avoid redundant token fetches.

## Key Classes

| Class | Purpose |
|-------|---------|
| `IdentityProvider` | Base class for all auth providers — Cognito, Okta, Entra, generic OAuth |
| `IdentityClient` | Orchestrates multiple providers, resolves credentials for named targets |
| `CredentialCache` | TTL-based in-process cache for tokens and API keys |

## Four Authentication Patterns

### 1. Inbound JWT Verification

Verify a JWT from the caller before processing the request. Use the `@requires_access_token` decorator:

```python
from agent_core.identity.decorators import requires_access_token

@app.entrypoint
@requires_access_token(issuer="https://cognito-idp.${AWS_REGION}.amazonaws.com/${USER_POOL_ID}")
async def handle(context):
    # context.identity.claims contains the verified JWT claims
    user_id = context.identity.claims["sub"]
    ...
```

The decorator rejects the invocation with a `401` if the token is missing, expired, or has an invalid signature. Supported issuers: Amazon Cognito, Okta, Microsoft Entra ID, and any standard OIDC provider.

### 2. Outbound API Key

Retrieve a stored API key to call an external service:

```python
from agent_core.identity import IdentityClient

identity = IdentityClient.from_blueprint("agent.yaml")

# Fetches from Secrets Manager, caches for TTL
api_key = await identity.get_api_key("weather-service")

response = await httpx.get(
    "https://api.weather.example.com/forecast",
    headers={"X-API-Key": api_key},
)
```

The key name (`"weather-service"`) maps to a secret ARN declared in the blueprint. The `CredentialCache` stores the resolved value for the TTL period, defaulting to the secret's rotation interval.

### 3. Three-Legged OAuth (User-Delegated)

Exchange an authorization code or refresh token for a user-scoped access token:

```python
# Exchange refresh token stored for this user
token = await identity.get_oauth_token(
    provider="my-crm",
    user_id=context.identity.claims["sub"],
    scopes=["read:contacts", "write:notes"],
)

response = await httpx.get(
    "https://api.crm.example.com/contacts",
    headers={"Authorization": f"Bearer {token.access_token}"},
)
```

The provider configuration (client ID, token URL, scopes) is declared in the blueprint. Refresh token rotation is handled automatically.

### 4. Machine-to-Machine (M2M) OAuth

Acquire a client credentials grant for service-to-service calls:

```python
from agent_core.identity.decorators import requires_api_key

@app.entrypoint
@requires_api_key(header="X-Agent-Key", secret_name="inbound-agent-key")
async def handle(context):
    # Caller provided the correct API key
    ...
```

For outbound M2M, call `identity.get_m2m_token(provider="...")`. The `CredentialCache` prevents redundant token requests for the token's lifetime.

## CredentialCache

The cache is TTL-based and keyed by `(provider_name, user_id, scope_hash)`:

```python
from agent_core.identity import CredentialCache

cache = CredentialCache(default_ttl_seconds=300)

# Manually populate (useful in tests)
cache.put("my-service", token_value, ttl_seconds=600)

# Check before fetching
if not cache.has("my-service"):
    token = await fetch_token()
    cache.put("my-service", token)
```

Cache entries are invalidated automatically on expiry. There is no distributed cache — each container instance maintains its own. For short-lived containers this is sufficient; for long-lived instances, TTLs ensure tokens are refreshed before expiry.

## Blueprint Configuration

```yaml
identity:
  inbound:
    type: cognito
    user_pool_id: "${COGNITO_USER_POOL_ID}"
    region: "${AWS_REGION}"

  outbound:
    - name: crm-api
      type: api_key
      secret_arn: "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:crm-api-key"

    - name: data-platform
      type: oauth2_m2m
      token_url: "https://auth.example.com/oauth/token"
      client_id_secret: "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:dp-client-id"
      client_secret_secret: "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:dp-client-secret"
      scopes: ["read:data", "write:data"]

  credential_cache:
    ttl_seconds: 300
```

## Provider Implementations

| Provider Class | Identity System | Notes |
|----------------|-----------------|-------|
| `CognitoProvider` | Amazon Cognito | Validates JWTs via JWKS endpoint |
| `OktaProvider` | Okta | Supports OIDC and OAuth 2.0 |
| `EntraProvider` | Microsoft Entra ID | Supports tenant-scoped and multi-tenant apps |
| `GenericOIDCProvider` | Any OIDC issuer | Falls back to standard OIDC discovery |

Custom providers implement `IdentityProvider` and override `verify_token` and `get_token`.
