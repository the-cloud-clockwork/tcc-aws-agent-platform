---
title: Amazon Bedrock
nav_order: 2
parent: Inference Providers
---

# Amazon Bedrock

`provider: bedrock` is the default inference provider. It routes model calls through the [Amazon Bedrock Converse API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html) using the Strands SDK `BedrockModel`. No API key is needed — authentication is handled entirely through IAM.

## Required environment variable

| Variable | Purpose |
|----------|---------|
| `BEDROCK_REGION` | AWS region where Bedrock model requests are sent. **Required.** The loader raises `BlueprintLoadError` at startup if this variable is absent. |

{: .warning }
> There is no `region` field in the `model:` block. The Bedrock region must be set as an environment variable. This is a deliberate separation: the blueprint declares *what* model to use; the deployment environment declares *where* it is accessed.

## Blueprint configuration

```yaml
model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  temperature: 0.3
  max_tokens: 4096
```

All four fields are required. `provider` defaults to `bedrock`, so you may omit it:

```yaml
model:
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  temperature: 0.1
  max_tokens: 8192
```

### Runtime-switchable model IDs

Use `${VAR:-default}` expansion to select the model at deploy time without changing the blueprint file:

```yaml
model:
  provider: bedrock
  model_id: ${BEDROCK_MODEL_ID:-us.anthropic.claude-sonnet-4-20250514-v1:0}
  temperature: 0.1
  max_tokens: 8192
```

Set `BEDROCK_MODEL_ID` in the Runtime environment variables (via the agents Terraform module) to override the default at deploy time.

## Model IDs

Bedrock model IDs are region-qualified. Cross-region inference profiles use the `us.` or `eu.` prefix:

```
# US cross-region inference profile
us.anthropic.claude-sonnet-4-20250514-v1:0
us.anthropic.claude-haiku-4-20250514-v1:0

# Direct regional model
anthropic.claude-3-5-sonnet-20241022-v2:0

# Amazon Nova
us.amazon.nova-pro-v1:0
```

Refer to the [Amazon Bedrock model IDs documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html) for the full current list. Model availability varies by region — verify the model is available in your `BEDROCK_REGION` before deploying.

## IAM requirements

The agent's IAM role (provisioned by `modules/agents/iam.tf`) needs `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` on the target model ARN, plus cross-region inference profile ARNs when using `us.*`/`eu.*` prefixed IDs.

The `modules/platform/modules/agentcore/` sub-module provisions the Gateway IAM role with the required Bedrock permissions. The per-agent role in `modules/agents/iam.tf` holds the runtime-level model invocation rights.

## Bedrock Guardrails

When `data_protection.provider: bedrock` is set in the observability block, the platform registers a `GuardrailHook` that calls Bedrock's `ApplyGuardrail` API on agent I/O. This guard only activates when **both** conditions are met:

1. `model.provider: bedrock`
2. `BEDROCK_GUARDRAIL_ID` environment variable is set

If either condition is absent, the Bedrock guardrail hook is silently skipped — no error is raised. For non-Bedrock providers, use `data_protection.provider: presidio` for provider-agnostic in-process PII filtering. See [Data Protection](../observability/data-protection) for the full comparison.

```yaml
observability:
  data_protection:
    provider: bedrock   # Only activates when model.provider is also bedrock
    # BEDROCK_GUARDRAIL_ID and BEDROCK_GUARDRAIL_VERSION must be set as env vars
    # guardrail_id_env: BEDROCK_GUARDRAIL_ID        # Override env var name if needed
    # guardrail_version_env: BEDROCK_GUARDRAIL_VERSION
```

## Extended thinking

The `thinking:` top-level block in the blueprint enables Claude's extended thinking mode on Bedrock:

```yaml
model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  temperature: 0.1
  max_tokens: 16384

thinking:
  enabled: true
  budget_tokens: 10000   # Tokens reserved for the thinking phase
```

Extended thinking is currently only meaningful with Claude models on Bedrock. The `budget_tokens` value must be less than `max_tokens`.

## Prompt caching

Bedrock supports prompt caching. The `cache_prompt` and `cache_tools` fields control the caching policy:

```yaml
model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  temperature: 0.1
  max_tokens: 4096
  cache_prompt: default   # default | none | <custom-cache-key>
  cache_tools: default
```

These fields are passed through to the Strands `BedrockModel`. Refer to [Amazon Bedrock prompt caching documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html) for model-specific caching support and pricing.

---

Related: [Structured Output](structured-output) — `output_schema` works with Bedrock using the Strands native forced-tool path.
