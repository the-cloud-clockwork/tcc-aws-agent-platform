---
title: Inference Providers
nav_order: 5
has_children: true
---

# Inference Providers

AWS Agent Platform is provider-agnostic by design. A single blueprint field — `model.provider` — selects the inference backend: Amazon Bedrock, the direct Anthropic API, any OpenAI-compatible endpoint via LiteLLM, or Google Vertex AI (Gemini). Switching providers requires no code changes — only a blueprint update.

## The four providers

| Value | Backend | Primary use case |
|-------|---------|-----------------|
| `bedrock` | Amazon Bedrock Converse API | Default. AWS-native. GuardRails, FIPS, PrivateLink. |
| `anthropic` | Anthropic API directly | Direct Anthropic access without AWS mediation. |
| `litellm` | Any OpenAI-compatible endpoint via LiteLLM | Self-hosted proxy, vLLM, Ollama, OpenRouter, Cloudflare AI Gateway, or any custom router. |
| `vertex` | Google Vertex AI (Gemini models) | GCP-hosted Gemini models. |

## How provider dispatch works

The `BlueprintLoader._build_model_config()` method reads `model.provider` and constructs the appropriate Strands SDK model instance via a `match/case` dispatch. All provider imports are **lazy** — non-default provider packages are only imported when the blueprint actually selects them, so unused SDK packages have zero startup cost.

The dispatch is exhaustive: an unknown `provider` value raises `BlueprintLoadError` immediately at load time, before any inference request is made.

## In this section

- [Overview](overview) — how to choose a provider and what each delivers
- [Amazon Bedrock](bedrock) — region setup, model IDs, IAM
- [Anthropic](anthropic) — direct API, api_key_env
- [LiteLLM](litellm) — proxy configuration, headers, the `custom_llm_provider` mechanism, CVE safety pin
- [Google Vertex AI](vertex) — GCP credentials, what is and is not forwarded
- [Structured Output](structured-output) — `output_schema`, Strands native forced-tool path, minimum SDK version
