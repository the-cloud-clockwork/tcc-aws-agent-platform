---
title: Data Protection
nav_order: 5
parent: "Observability & Evaluation"
---

# Data Protection

The platform provides two independent layers of PII protection. Layer 1 filters PII in-process before it reaches any observability backend. Layer 2 masks PII patterns in CloudWatch log streams at rest. Both layers are configured in the blueprint's `observability.data_protection` block.

## Two-layer model

```
Agent I/O
    │
    ▼
┌─────────────────────────────────────────────────┐
│  Layer 1 — In-process filtering                 │
│                                                 │
│  provider: bedrock   → Bedrock Guardrails       │
│  provider: presidio  → Microsoft Presidio       │
│  provider: none      → No in-process filtering  │
└─────────────────────────────────────────────────┘
    │
    ▼
Traces, Langfuse spans, audit records
    │
    ▼
┌─────────────────────────────────────────────────┐
│  Layer 2 — CloudWatch log masking               │
│                                                 │
│  Masks PII patterns in log streams at rest.     │
│  Active when cloudwatch_masking_identifiers     │
│  is non-empty. Independent of Layer 1.          │
└─────────────────────────────────────────────────┘
    │
    ▼
CloudWatch Logs (stored)
```

Together these two layers provide defense in depth: Layer 1 reduces PII at the source before data leaves the agent process; Layer 2 catches residual leakage at the storage layer.

## Layer 1 — In-process filtering

### data_protection.provider: bedrock (default)

Uses AWS Bedrock Guardrails to anonymize PII in agent I/O. The guardrail intercepts model inputs and outputs and applies PII masking, content filtering, and topic restrictions.

**Requirements:**
- `blueprint.model.provider` must be `bedrock` — Bedrock Guardrails requires a Bedrock model. This provider has no effect on LiteLLM, Anthropic, or Vertex agents.
- `BEDROCK_GUARDRAIL_ID` env var must be set (env var name is configurable via `guardrail_id_env`)
- `BEDROCK_GUARDRAIL_VERSION` env var must be set (env var name is configurable via `guardrail_version_env`)

If either env var is absent, the guardrail is silently skipped — the agent runs without PII filtering rather than crashing.

```yaml
observability:
  data_protection:
    provider: bedrock
    guardrail_id_env: BEDROCK_GUARDRAIL_ID        # default
    guardrail_version_env: BEDROCK_GUARDRAIL_VERSION  # default
```

The Bedrock guardrail operates at two integration points:

1. **`GuardrailHook`** — registered as a Strands hook, fires on agent I/O events to intercept content before it is processed or returned
2. **`build_pii_filter()`** — produces a callable used by `LangfuseHook` to sanitize conversation text before it is sent to Langfuse

These are separate surfaces protecting different data flows. The hook protects the agent I/O path; the Langfuse filter protects the observability path.

### data_protection.provider: presidio

Uses [Microsoft Presidio](https://microsoft.github.io/presidio/) (MIT-licensed) to detect and redact PII in-process. Presidio works with **any inference provider** — LiteLLM, Anthropic direct, OpenAI-compatible, Vertex — making it the correct choice for non-Bedrock deployments.

**Requirements:**
- Install the `presidio` extra: `pip install 'agent-core[presidio]'` (adds `presidio-analyzer` and `presidio-anonymizer`)

Presidio engines are **lazy-loaded** on the first hook invocation — there is no startup cost until the hook actually fires.

```yaml
observability:
  data_protection:
    provider: presidio
    presidio_entities:                     # empty = Presidio default set
      - EMAIL_ADDRESS
      - PHONE_NUMBER
      - CREDIT_CARD
      - US_SSN
      - PERSON
    presidio_language: en                  # analyzer language code
```

`presidio_entities` controls which entity types Presidio detects. An empty list activates Presidio's default detection set (EMAIL_ADDRESS, PHONE_NUMBER, PERSON, and others). See the [Presidio documentation](https://microsoft.github.io/presidio/supported_entities/) for the full entity type list.

`presidio_language` sets the analyzer language. English (`en`) is the default; Presidio supports multiple languages when the corresponding model is installed.

The `PresidioGuardrailHook` is registered as a Strands `HookProvider` with callbacks on `BeforeInvocationEvent` and `AfterInvocationEvent`. It logs when redaction occurs but does not expose the redacted content.

### data_protection.provider: none

Disables in-process PII filtering entirely. No `GuardrailHook` or `PresidioGuardrailHook` is registered. Use this when PII is handled upstream of the agent, or in development environments where filtering is not needed.

```yaml
observability:
  data_protection:
    provider: none
```

CloudWatch Layer 2 masking (see below) remains active regardless of this setting when `cloudwatch_masking_identifiers` is non-empty.

## Layer 2 — CloudWatch log masking

CloudWatch Data Protection masks PII patterns in log streams at rest. It is independent of the `provider` selection — it applies whether Layer 1 is `bedrock`, `presidio`, or `none`.

```yaml
observability:
  data_protection:
    cloudwatch_masking_identifiers:
      - EmailAddress
      - CreditCardNumber
      - USPhoneNumber
      - USSocialSecurityNumber
      - IpAddress
```

Identifier names follow the [CloudWatch Logs Data Protection](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/mask-sensitive-log-data-types.html) naming convention (PascalCase, no underscore). The platform creates a CloudWatch Data Protection policy with both an `Audit` statement (logs findings) and a `Deidentify` statement (masks the content with `MaskConfig`).

The policy is applied to the agent's log group at deploy time via `apply_log_data_protection()`. Even if PII leaks through Layer 1 and reaches a CloudWatch log stream, it is masked before being stored permanently.

## Provider selection guide

| Scenario | Recommended provider |
|---|---|
| Bedrock model, AWS-only deployment | `bedrock` |
| LiteLLM, Anthropic, Vertex provider | `presidio` |
| PII handled upstream, dev environment | `none` |
| Defense in depth (any provider) | `presidio` + `cloudwatch_masking_identifiers` |

## Full blueprint example

```yaml
observability:
  data_protection:
    # Layer 1: choose one
    provider: presidio
    presidio_entities:
      - EMAIL_ADDRESS
      - PHONE_NUMBER
      - CREDIT_CARD
    presidio_language: en

    # Layer 2: CloudWatch log masking (independent of provider)
    cloudwatch_masking_identifiers:
      - EmailAddress
      - CreditCardNumber
      - USPhoneNumber
```

## See also

- [Langfuse](langfuse) — the `pii_filter` callable sanitizes content before it reaches Langfuse traces
- [AWS-native](aws-native) — CloudWatch log groups where Layer 2 masking applies
- [Inference Providers](../inference) — `data_protection.provider: bedrock` requires `model.provider: bedrock`
