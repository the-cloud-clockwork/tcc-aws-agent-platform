---
title: "Observability & Evaluation"
nav_order: 6
has_children: true
---

# Observability & Evaluation

Every agent invocation produces a full execution trace — LLM calls, tool calls, token counts, latency, and errors — exported via OpenTelemetry to AWS CloudWatch. Alongside AWS-native tracing, the platform provides first-class **Langfuse** integration, cost tracking, provider-agnostic data protection (Bedrock Guardrails and Microsoft Presidio), and an evaluation framework that uses an LLM-as-judge to score agent behavior against real sessions.

## AWS-native or Langfuse — your choice

The platform treats observability as a configuration decision, not a hard dependency on any one backend.

| Capability | AWS-native path | Langfuse path |
|---|---|---|
| Distributed traces | CloudWatch / X-Ray via OTEL | Langfuse traces via `LangfuseHook` |
| Token metrics | CloudWatch GenAI metrics | Langfuse generation spans |
| Evaluation | Bedrock AgentCore Evaluation | `LangfuseEvaluationClient` |
| Dashboard | CloudWatch GenAI Observability | Langfuse Projects UI |

Both paths can be active simultaneously — this is the recommended production setup. CloudWatch handles infrastructure alerting and retention; Langfuse handles prompt debugging and cost analysis. See the [Langfuse](observability/langfuse) page for the intentional double-trace design.

## What this section covers

- **[Observability overview](observability/observability)** — OTEL trace anatomy, session baggage, custom spans, activation checklist
- **[AWS-native](observability/aws-native)** — OTEL auto-instrumentation, CloudWatch GenAI metrics, Transaction Search, vended logs
- **[Langfuse](observability/langfuse)** — `LangfuseHook`, double-trace design, full conversation capture
- **[Cost tracking](observability/cost-tracking)** — `CostTracker`, built-in pricing defaults, `MODEL_PRICING` env var
- **[Data protection](observability/data-protection)** — Bedrock Guardrails vs Microsoft Presidio, CloudWatch log masking
- **[Evaluation](observability/evaluation)** — 12 built-in evaluators, agentcore vs langfuse providers, custom LLM-as-judge

## Master toggle

The `observability.enabled` field in a blueprint is the master toggle for all application-level observability features (Langfuse, audit log, structured logger, cost tracker). Set it to `false` to disable all of them for a given agent:

```yaml
observability:
  enabled: false   # disables LangfuseHook, AuditLogWriter, CostTracker, StructuredLogger
```

OTEL auto-instrumentation (the `opentelemetry-instrument` wrapper in the Dockerfile) is controlled separately by the Terraform variable `runtime.observability_enabled` and is not affected by this blueprint flag.
