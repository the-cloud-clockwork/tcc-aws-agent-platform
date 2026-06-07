---
title: Overview
nav_order: 1
parent: Inference Providers
---

# Inference Provider Overview

AWS Agent Platform decouples the agent definition from the inference backend. The same agent blueprint, system prompt, tools, memory, and observability configuration run on any of the four supported providers without any Python code changes. The only difference is the `model:` block in the blueprint YAML.

## The `model:` block

Every agent blueprint contains a `model:` block with four fields that apply to all providers, plus optional fields used by specific providers:

```yaml
model:
  provider: bedrock             # bedrock | anthropic | litellm | vertex  (default: bedrock)
  model_id: <model-identifier>  # Required. Provider-specific model ID string.
  temperature: 0.3              # Required. 0.0–1.0. Controls sampling randomness.
  max_tokens: 4096              # Required. Maximum output tokens per response.

  # Optional — provider-specific
  base_url: https://...         # API base URL. Used by litellm for proxy routing.
  api_key_env: MY_API_KEY       # Env var name holding the API key (never the key itself).
  extra_headers_env:            # HTTP header name → env var name map. Resolved at load time.
    CF-Access-Client-Id: CF_CLIENT_ID
    CF-Access-Client-Secret: CF_CLIENT_SECRET
  cache_prompt: default         # Prompt caching policy: default | none | <custom-key>
  cache_tools: default          # Tool-result caching policy.
```

{: .note }
> `provider` defaults to `bedrock`. All other fields except `model_id`, `temperature`, and `max_tokens` are optional. The platform raises `BlueprintLoadError` at startup if a required provider-specific environment variable is absent.

### `model_id` env-template expansion

The `model_id` value supports `${VAR}` and `${VAR:-default}` expansion at load time for the `bedrock`, `anthropic`, and `litellm` providers. The `vertex` provider uses `os.path.expandvars()` for the same purpose. This lets you switch models at runtime without rebuilding the image:

```yaml
model:
  provider: litellm
  model_id: ${ACTIVE_MODEL:-claude-sonnet-4-6}   # Falls back to claude-sonnet-4-6 if unset
  temperature: 0.3
  max_tokens: 8192
  base_url: https://your-litellm-proxy.example.com
  api_key_env: LITELLM_API_KEY
```

## How to choose a provider

### Use `bedrock` when

- You are deploying entirely within AWS and want native service integration (VPC endpoints, PrivateLink, FIPS endpoints, CloudTrail logging of model invocations).
- You need Bedrock Guardrails for PII filtering at the API level.
- Your organization's IAM policies govern model access through resource-level policies.

### Use `anthropic` when

- You want to call Anthropic's API directly, bypassing Bedrock.
- You have a direct Anthropic contract or need access to models not yet available on Bedrock.
- You are building and testing locally against the production Anthropic API.

### Use `litellm` when

- You run a self-hosted LiteLLM proxy (or any OpenAI-compatible router such as vLLM, Ollama, OpenRouter, or Cloudflare AI Gateway).
- You want a single routing layer that can transparently switch between multiple upstream providers, apply rate limiting, load-balance, or add audit logging.
- You are in a cost-optimization workflow that compares multiple models — a LiteLLM proxy abstracts all provider differences behind a single `base_url`.

### Use `vertex` when

- You need Google Gemini models on Vertex AI.
- Your workload runs in a mixed GCP/AWS environment.

## What does not change across providers

Switching providers does not affect anything outside the `model:` block:

- **Prompt** — resolved from the same Prompt Registry entry.
- **Tools** — Gateway MCP tools, built-in tools, and A2A tool declarations are all provider-agnostic.
- **Memory** — short-term and long-term memory hooks fire identically.
- **Observability** — Langfuse, OTEL, audit log, and cost tracking are all provider-agnostic (see [Observability & Evaluation](../observability)).
- **Policy** — Cedar access control evaluates the same rules regardless of model.
- **Structured output** — `output_schema` uses the Strands native forced-tool path on all four providers (see [Structured Output](structured-output)).

## Provider capability matrix

| Capability | bedrock | anthropic | litellm | vertex |
|-----------|---------|-----------|---------|--------|
| `temperature` forwarded | Yes | No¹ | Yes | No¹ |
| `max_tokens` forwarded | Yes | Yes | Yes | No¹ |
| `api_key_env` wired | N/A² | Yes | Yes | No |
| `base_url` wired | No | No | Yes | No |
| `extra_headers_env` wired | No | No | Yes | No |
| Bedrock Guardrails | Yes³ | No | No | No |
| Presidio PII filter | No | Yes | Yes | Yes |

¹ These fields are accepted in the blueprint schema but are not forwarded to the provider constructor for this backend. Set sampling parameters in the model's API defaults or proxy-side configuration.

² Bedrock uses IAM credentials via the AWS SDK — no API key is needed.

³ Bedrock Guardrails also require `BEDROCK_GUARDRAIL_ID` to be set. See [Amazon Bedrock](bedrock).

---

Next: [Amazon Bedrock](bedrock) — the default provider and how to configure it.
