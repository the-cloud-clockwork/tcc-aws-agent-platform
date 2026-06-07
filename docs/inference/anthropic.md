---
title: Anthropic
nav_order: 3
parent: Inference Providers
---

# Anthropic

`provider: anthropic` calls the Anthropic API directly, bypassing Amazon Bedrock. It uses the Strands SDK `AnthropicModel` backed by the `anthropic` Python client library.

## Installation

The `anthropic` extra is required:

```bash
pip install "agent-core[anthropic]"
```

This installs `anthropic>=0.30,<1` alongside `agent-core`.

## Blueprint configuration

```yaml
model:
  provider: anthropic
  model_id: claude-sonnet-4-5-20250908    # Anthropic model string, no region prefix
  temperature: 0.3
  max_tokens: 4096
  api_key_env: ANTHROPIC_API_KEY          # Env var holding the Anthropic API key
```

### Fields

| Field | Required | Notes |
|-------|----------|-------|
| `model_id` | Yes | Anthropic model identifier (e.g. `claude-sonnet-4-5-20250908`). |
| `temperature` | Yes | Accepted in the blueprint schema but **not forwarded** to `AnthropicModel` — the constructor does not accept a temperature parameter. Set sampling defaults in your Anthropic API account or use a LiteLLM proxy if you need per-request temperature control. |
| `max_tokens` | Yes | Forwarded to `AnthropicModel` as a constructor argument. |
| `api_key_env` | Recommended | Name of the environment variable holding the Anthropic API key. The key value is never stored in the blueprint. If the env var is absent or empty, the `anthropic` client uses its own default resolution (the `ANTHROPIC_API_KEY` env var). |

{: .warning }
> `temperature` is a required field in the `model:` schema for all providers, but it is **not forwarded to the Anthropic provider constructor**. If precise temperature control is important for your use case, route through [LiteLLM](litellm) — the LiteLLM provider passes `temperature` in the `params` dict.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` (or whatever `api_key_env` names) | Anthropic API key. Resolved at load time from the env var named in `api_key_env`. |

No region variable is needed — the Anthropic API is a single global endpoint (`https://api.anthropic.com`).

## Runtime-switchable model IDs

The `model_id` field supports `${VAR:-default}` expansion:

```yaml
model:
  provider: anthropic
  model_id: ${ANTHROPIC_MODEL:-claude-haiku-4-20250514}
  temperature: 0.1
  max_tokens: 4096
  api_key_env: ANTHROPIC_API_KEY
```

## Example: minimal Anthropic agent

```yaml
id: research-assistant
name: Research Assistant
version: "1.0.0"
prompt_ref: research-assistant-system-v1

model:
  provider: anthropic
  model_id: claude-sonnet-4-5-20250908
  temperature: 0.3
  max_tokens: 8192
  api_key_env: ANTHROPIC_API_KEY

gateway:
  auth_type: aws_iam

runtime:
  type: agentcore
  max_iterations: 10
  idle_timeout_minutes: 15
  network_mode: PUBLIC
  protocol: HTTP
```

## Data protection

Bedrock Guardrails are not available for the Anthropic provider. Use `data_protection.provider: presidio` for provider-agnostic in-process PII filtering:

```yaml
observability:
  data_protection:
    provider: presidio
    presidio_entities:
      - EMAIL_ADDRESS
      - PHONE_NUMBER
      - CREDIT_CARD
    presidio_language: en
```

See [Data Protection](../observability/data-protection) for setup instructions.

---

Related: [LiteLLM](litellm) — if you need temperature control, header injection, or proxy routing with Claude models, the LiteLLM provider is the better fit.
