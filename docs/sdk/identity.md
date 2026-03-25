---
title: Identity
nav_order: 3
parent: SDK Reference
---

# Identity

The Identity subsystem manages all authentication and credential flows for agents. It handles outbound auth (acquiring credentials to call external systems), with an in-process credential cache to avoid redundant token fetches.

> **Note:** Workload identity CRUD (creating credential providers, registering OAuth clients) is handled automatically by the platform from blueprint YAML. The Identity subsystem provides runtime decorators and wiring so your agent code receives the correct tokens at invocation time.

## Key Classes

| Class | Purpose |
|-------|---------|
| `IdentityWiring` | Bridge between blueprint credential config and runtime decorators |
| `CredentialCache` | TTL-based in-process cache for tokens and API keys |
| `requires_access_token` | Decorator — injects an OAuth2 access token into the wrapped function |
| `requires_api_key` | Decorator — injects an API key from Secrets Manager into the wrapped function |

## Three Authentication Patterns

### 1. Machine-to-Machine (M2M) OAuth

Acquire a client credentials grant for service-to-service calls. Use the `@requires_access_token` decorator with `auth_flow="M2M"`:

```python
from agent_core.identity.decorators import requires_access_token

@requires_access_token(auth_flow="M2M", provider_name="data-platform")
async def call_data_api(query: str, *, access_token: str) -> str:
    response = await httpx.get(
        "https://api.example.com/data",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": query},
    )
    return response.text
```

The decorator resolves a client credentials token from the named credential provider registered in AgentCore Identity. The token is injected into the `access_token` keyword argument (configurable via the `into` parameter).

### 2. Three-Legged OAuth (User-Delegated)

Exchange a refresh token for a user-scoped access token. Use `@requires_access_token` with `auth_flow="USER_FEDERATION"`:

```python
from agent_core.identity.decorators import requires_access_token

def on_auth_url(url: str) -> None:
    # Present this URL to the user for authorization
    print(f"Please visit: {url}")

@requires_access_token(
    auth_flow="USER_FEDERATION",
    provider_name="my-crm",
    scopes=["read:contacts", "write:notes"],
    on_auth_url=on_auth_url,
    callback_url="https://myapp.example.com/callback",
)
async def get_contacts(*, access_token: str) -> str:
    response = await httpx.get(
        "https://api.crm.example.com/contacts",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    return response.text
```

For 3LO, the `on_auth_url` callback is invoked with the authorization URL when user consent is needed. The default callback logs the URL at WARNING level.

### 3. Outbound API Key

Retrieve a stored API key to call an external service:

```python
from agent_core.identity.decorators import requires_api_key

@requires_api_key(provider_name="weather-service")
def call_weather(city: str, *, api_key: str) -> str:
    response = httpx.get(
        "https://api.weather.example.com/forecast",
        headers={"X-API-Key": api_key},
        params={"city": city},
    )
    return response.text
```

The provider name maps to an API key credential provider registered in AgentCore Identity. The resolved key is injected into the `api_key` keyword argument (configurable via the `into` parameter).

## IdentityWiring (Blueprint Integration)

`IdentityWiring` bridges blueprint credential configuration and runtime decorators. It is created automatically during `build_agent_session()` and provides decorator factories:

```python
with loader.build_agent_session("my-agent") as session:
    # Get a decorator for a named credential
    dec = session.identity.get_api_key_decorator("external-api")

    @tool
    def call_external(query: str) -> str:
        @dec
        def _inner(*, api_key: str) -> str:
            return requests.get(url, headers={"X-API-Key": api_key}).text
        return _inner()
```

This nested-function pattern is the standard way to use Identity in domain tool functions. The wiring resolves the correct provider name, scopes, and auth flow from the blueprint configuration.

## Decorator Reference

### `requires_access_token`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider_name` | `str` | required | Name of credential provider in AgentCore Identity |
| `scopes` | `list[str]` | `None` | OAuth2 scopes to request |
| `auth_flow` | `str` | `"M2M"` | `"USER_FEDERATION"` (3LO) or `"M2M"` |
| `on_auth_url` | `Callable[[str], None]` | logs at WARNING | Callback for 3LO authorization URL |
| `callback_url` | `str` | `None` | OAuth2 redirect URL (3LO only) |
| `into` | `str` | `"access_token"` | Keyword argument name to inject the token into |
| `force_authentication` | `bool` | `False` | Force re-authentication even if a valid token exists |

### `requires_api_key`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider_name` | `str` | required | Name of API key credential provider |
| `into` | `str` | `"api_key"` | Keyword argument name to inject the key into |

## CredentialCache

The cache is TTL-based and prevents redundant token fetches:

```python
from agent_core.identity.cache import CredentialCache

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
  credentials:
    - name: data-platform
      type: oauth2
      provider: data-platform-provider
      auth_flow: M2M
      scopes: ["read:data", "write:data"]

    - name: crm-api
      type: oauth2
      provider: crm-provider
      auth_flow: USER_FEDERATION
      scopes: ["read:contacts"]
      callback_url_env: CRM_CALLBACK_URL

    - name: weather-service
      type: api_key
      provider: weather-key-provider
```
