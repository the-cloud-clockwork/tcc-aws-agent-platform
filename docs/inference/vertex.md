---
title: Google Vertex AI
nav_order: 5
parent: Inference Providers
---

# Google Vertex AI

`provider: vertex` calls Google Vertex AI Gemini models using the Strands SDK `GeminiModel`. This provider is the choice for GCP-hosted Gemini inference in mixed GCP/AWS environments.

## Installation

The Strands SDK must be able to import `strands.models.gemini.GeminiModel`. This is included in `strands-agents>=1.0.0,<2` which is a core dependency of `agent-core`. No separate extra is required.

## Blueprint configuration

```yaml
model:
  provider: vertex
  model_id: gemini-2.0-flash-001    # Vertex AI model ID
  temperature: 0.3                  # Accepted in schema but NOT forwarded (see below)
  max_tokens: 4096                  # Accepted in schema but NOT forwarded (see below)
```

### Fields

| Field | Required | Notes |
|-------|----------|-------|
| `model_id` | Yes | Vertex AI model identifier. Supports `$VAR` env-var expansion via `os.path.expandvars()`. |
| `temperature` | Yes (schema) | **Not forwarded** to `GeminiModel`. Accepted by the schema but silently ignored at load time — configure sampling at the Vertex AI API or model level instead. |
| `max_tokens` | Yes (schema) | **Not forwarded** to `GeminiModel`. Accepted by the schema but silently ignored at load time. |
| `api_key_env` | No | **Not wired** for the vertex provider. GCP authentication uses ADC (see below). Any value set here has no effect. |
| `base_url` | No | **Not wired** for the vertex provider. Any value set here has no effect. |
| `extra_headers_env` | No | **Not wired** for the vertex provider. Any value set here has no effect. |

{: .warning }
> Only `model_id` is passed to the `GeminiModel` constructor. Every other field in the table above — `temperature`, `max_tokens`, `api_key_env`, `base_url`, and `extra_headers_env` — is accepted by the blueprint schema but **not forwarded**. No warning is emitted at load time. If you need per-request sampling control, deploy a LiteLLM proxy in front of Vertex AI and use `provider: litellm` instead.

## Authentication — Application Default Credentials

The vertex provider does not use API key authentication. It uses Google Application Default Credentials (ADC). The credential chain is:

1. `GOOGLE_APPLICATION_CREDENTIALS` environment variable pointing to a service account key JSON file.
2. Workload Identity Federation (recommended for production — no key file required).
3. `gcloud auth application-default login` (local development only).

For AgentCore Runtime deployments, configure Workload Identity Federation to allow the agent's IAM role to impersonate a GCP service account, or mount a service account key as a Kubernetes secret and set `GOOGLE_APPLICATION_CREDENTIALS`.

Additional environment variables used by the Vertex AI client:

| Variable | Purpose |
|----------|---------|
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account key JSON (when not using Workload Identity). |
| `VERTEX_PROJECT` | GCP project ID. Required by the Vertex AI client. |
| `VERTEX_LOCATION` | GCP region (e.g. `us-central1`). Required by the Vertex AI client. |

## Runtime-switchable model IDs

The `model_id` field supports standard shell variable expansion via `os.path.expandvars()`:

```yaml
model:
  provider: vertex
  model_id: ${VERTEX_MODEL_ID}   # Must be set in the environment; no :-default syntax
  temperature: 0.3
  max_tokens: 4096
```

{: .note }
> The vertex provider uses `os.path.expandvars()` rather than the platform's `${VAR:-default}` template expansion. This means the `:-default` fallback syntax is not available — if the env var is unset, `os.path.expandvars()` leaves `$VERTEX_MODEL_ID` as a literal string, which will cause a Vertex AI API error. Always set the env var explicitly.

## Example: Vertex AI agent

```yaml
id: gemini-analyst
name: Gemini Analyst
version: "1.0.0"
prompt_ref: gemini-analyst-system-v1

model:
  provider: vertex
  model_id: gemini-2.0-flash-001
  temperature: 0.3       # Required by schema; not forwarded to GeminiModel
  max_tokens: 8192       # Required by schema; not forwarded to GeminiModel

gateway:
  auth_type: aws_iam

runtime:
  type: agentcore
  max_iterations: 10
  idle_timeout_minutes: 15
  network_mode: PUBLIC
  protocol: HTTP

execution_modes:
  simulation: true
  staging: true
  production: false
```

## Supported models

Refer to the [Vertex AI model garden](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/models) for the current list of Gemini model IDs available on Vertex AI. Common values:

```
gemini-2.0-flash-001
gemini-2.0-pro-001
gemini-1.5-pro-001
gemini-1.5-flash-001
```

## Data protection

Bedrock Guardrails are not available for the vertex provider. Use `data_protection.provider: presidio` for provider-agnostic in-process PII filtering:

```yaml
observability:
  data_protection:
    provider: presidio
    presidio_entities:
      - EMAIL_ADDRESS
      - PHONE_NUMBER
    presidio_language: en
```

## Known limitations

- `temperature` and `max_tokens` specified in the blueprint are silently ignored at load time. There is no warning. Configure sampling at the Vertex AI API or model level.
- If you need per-request temperature or `max_tokens` control, deploy a LiteLLM proxy in front of Vertex AI and use `provider: litellm` — the LiteLLM provider forwards both parameters correctly.
- `api_key_env`, `base_url`, and `extra_headers_env` have no effect for this provider even if set in the blueprint.

---

Related: [LiteLLM](litellm) — if you need sampling parameter control or a proxy in front of Vertex AI. [Overview](overview) — full provider comparison matrix.
