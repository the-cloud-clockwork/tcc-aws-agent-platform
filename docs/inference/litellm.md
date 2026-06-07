---
title: LiteLLM
nav_order: 4
parent: Inference Providers
---

# LiteLLM

`provider: litellm` routes inference through any OpenAI-compatible HTTP endpoint using the Strands SDK `LiteLLMModel`. This covers self-hosted LiteLLM proxy servers, vLLM, Ollama (with the OpenAI adapter), OpenRouter, Cloudflare AI Gateway, and any other OpenAI-compatible API.

This is the provider to use when you want a single routing layer that can transparently switch between multiple upstream models, apply rate limiting, load-balance across instances, enforce budgets, or add custom audit logging — all without touching the agent blueprint.

## Installation

The `litellm` extra is required:

```bash
pip install "agent-core[litellm]"
```

This installs `litellm>=1.83.0,<2`. See [the CVE note](#cve-2026-33634-safety-pin) below for why the lower bound matters.

## Blueprint configuration

```yaml
model:
  provider: litellm
  model_id: claude-sonnet-4-6              # Model name as the proxy expects it
  temperature: 0.3
  max_tokens: 4096
  base_url: https://your-litellm-proxy.example.com
  api_key_env: LITELLM_API_KEY             # Env var holding the API key
```

### Fields

| Field | Required | Notes |
|-------|----------|-------|
| `model_id` | Yes | Model string passed through **unchanged** to the proxy. The proxy maps this to the upstream provider. |
| `temperature` | Yes | Forwarded to LiteLLM via the `params` dict (`params={"temperature": ..., "max_tokens": ...}`). |
| `max_tokens` | Yes | Forwarded to LiteLLM via the `params` dict. |
| `base_url` | Recommended | Base URL of the proxy endpoint. Required when routing through a custom proxy. |
| `api_key_env` | Recommended | Env var name holding the API key. Never put the key itself in the blueprint. |
| `extra_headers_env` | Optional | Map of HTTP header name → env var name. Resolved at load time. Useful for auth headers such as Cloudflare Access tokens. |

### `extra_headers_env` — injecting custom headers

```yaml
model:
  provider: litellm
  model_id: claude-sonnet-4-6
  temperature: 0.3
  max_tokens: 4096
  base_url: https://your-gateway.example.com
  api_key_env: GATEWAY_API_KEY
  extra_headers_env:
    CF-Access-Client-Id: CF_ACCESS_CLIENT_ID
    CF-Access-Client-Secret: CF_ACCESS_CLIENT_SECRET
```

Each entry maps an HTTP header name (sent with every request) to the name of an environment variable whose value is resolved at load time. Headers whose env var is absent or empty are omitted silently.

## The `custom_llm_provider` mechanism

When `base_url` is set, the loader automatically sets `custom_llm_provider="openai"` inside `client_args`. This is a critical detail:

**Without this flag**, the `litellm` library inspects `model_id` and routes based on the name prefix — `claude-*` goes to Anthropic's API directly, `gemini-*` goes to Google, `deepseek-*` goes to DeepSeek, and so on — **completely ignoring `base_url`**. Your carefully configured proxy is bypassed.

**With this flag**, `litellm` treats the endpoint as OpenAI-compatible and sends all requests to `base_url`, regardless of what the model name looks like. This is the correct behavior when your proxy handles all routing internally.

The `model_id` string is passed through **unchanged** — no prefix is added. Supply whatever model identifier your proxy expects:

```yaml
# If your proxy expects the model as "claude-sonnet-4-6"
model_id: claude-sonnet-4-6

# If your proxy expects a fully-qualified Anthropic ID
model_id: anthropic/claude-sonnet-4-5-20250908

# If your proxy uses internal aliases
model_id: my-org/fast-claude
```

This mechanism applies only when `base_url` is set. If `base_url` is absent, `custom_llm_provider` is not injected and `litellm` resolves the provider from the model name as usual.

## Environment variables

| Variable | Purpose |
|----------|---------|
| Named by `api_key_env` | API key sent to the proxy. |
| Named by each entry in `extra_headers_env` | Custom HTTP header values resolved at load time. |

No region variable is needed — the endpoint is fully specified by `base_url`.

## Runtime-switchable model IDs

The `model_id` field supports `${VAR:-default}` expansion:

```yaml
model:
  provider: litellm
  model_id: ${ACTIVE_MODEL:-claude-sonnet-4-6}
  temperature: 0.3
  max_tokens: 8192
  base_url: https://your-litellm-proxy.example.com
  api_key_env: LITELLM_API_KEY
```

Set `ACTIVE_MODEL` in the Runtime environment to switch models across deployments without changing the blueprint.

## Example: agent behind a LiteLLM proxy

```yaml
id: analysis-agent
name: Analysis Agent
version: "1.0.0"
prompt_ref: analysis-agent-system-v1

model:
  provider: litellm
  model_id: ${ACTIVE_MODEL:-claude-sonnet-4-6}
  temperature: 0.2
  max_tokens: 8192
  base_url: https://llm.your-company.example.com
  api_key_env: LITELLM_API_KEY

gateway:
  auth_type: aws_iam

runtime:
  type: agentcore
  max_iterations: 10
  idle_timeout_minutes: 20
  network_mode: PRIVATE
  protocol: HTTP

execution_modes:
  simulation: true
  staging: true
  production: true
```

## Example: Cloudflare AI Gateway with Access tokens

```yaml
model:
  provider: litellm
  model_id: claude-sonnet-4-6
  temperature: 0.3
  max_tokens: 4096
  base_url: https://gateway.ai.cloudflare.com/v1/YOUR_ACCOUNT_ID/YOUR_GATEWAY/openai
  api_key_env: CF_GATEWAY_API_KEY
  extra_headers_env:
    CF-Access-Client-Id: CF_ACCESS_CLIENT_ID
    CF-Access-Client-Secret: CF_ACCESS_CLIENT_SECRET
```

## CVE-2026-33634 safety pin

The `litellm` dependency is pinned to `>=1.83.0,<2`. Versions 1.82.7 and 1.82.8 were compromised in a supply chain attack (CVE-2026-33634) that injected malicious code into the published PyPI packages.

If you pin or override `litellm` in your own `pyproject.toml` or `requirements.txt`, ensure the version is outside the `1.82.7–1.82.8` range. The `agent-core[litellm]` extra enforces `>=1.83.0` automatically.

## Structured output

`output_schema` works with the LiteLLM provider via the Strands native forced-tool path, as it does with all four providers. See [Structured Output](structured-output) for details.

## Data protection

Bedrock Guardrails are not available for the LiteLLM provider. Use `data_protection.provider: presidio` for provider-agnostic in-process PII filtering:

```yaml
observability:
  data_protection:
    provider: presidio
    presidio_entities:
      - EMAIL_ADDRESS
      - PHONE_NUMBER
    presidio_language: en
```

---

Related: [Overview](overview) — provider selection guide. [Structured Output](structured-output) — how `output_schema` works across all providers.
