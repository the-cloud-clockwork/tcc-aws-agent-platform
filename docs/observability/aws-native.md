---
title: AWS-Native Observability
nav_order: 2
parent: "Observability & Evaluation"
---

# AWS-Native Observability

The platform's AWS-native observability stack is built on three pillars: OpenTelemetry auto-instrumentation (ADOT), CloudWatch GenAI Observability metrics, and CloudWatch Vended Logs. Together they give you distributed traces, semantic metrics, and structured logs without writing instrumentation code.

## OTEL auto-instrumentation

Observability is configured via environment variables, not programmatic initialization. The Terraform `modules/agents` module injects these variables automatically into every agent container when `observability_enabled = true` (the default).

The generated Dockerfile wraps the entrypoint with `opentelemetry-instrument`:

```dockerfile
RUN pip install --no-cache-dir aws-opentelemetry-distro
CMD ["opentelemetry-instrument", "python", "-m", "app"]
```

No code changes are needed. The OTEL auto-instrumentation hooks into Strands' internal execution graph and exports traces to CloudWatch X-Ray automatically.

### Injected environment variables

| Variable | Value | Purpose |
|---|---|---|
| `AGENT_OBSERVABILITY_ENABLED` | `true` | Master toggle for ADOT auto-instrumentation |
| `OTEL_PYTHON_DISTRO` | `aws_distro` | Use the AWS OTEL distro |
| `OTEL_PYTHON_CONFIGURATOR` | `aws_configurator` | Use the AWS OTEL configurator |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | OTLP transport protocol |
| `OTEL_TRACES_EXPORTER` | `otlp` | Export traces via OTLP |
| `OTEL_RESOURCE_ATTRIBUTES` | `service.name={agent_id},aws.log.group.names=...` | Resource identity for CloudWatch |
| `OTEL_EXPORTER_OTLP_LOGS_HEADERS` | `x-aws-log-group=...,x-aws-log-stream=runtime-logs,...` | Log routing to the correct CloudWatch group |

To disable ADOT in favor of an external observability platform (Datadog, Dynatrace, Honeycomb), set `DISABLE_ADOT_OBSERVABILITY=true` in the blueprint's custom environment variables.

### What OTEL traces capture

- Agent invocation start and end with total latency
- Each LLM call: model ID, input/output token counts, stop reason
- Each tool call: tool name, serialized parameters, result sizes
- Memory read and write operations
- Exceptions with stack traces and which step failed

## CloudWatch GenAI metrics

AgentCore publishes GenAI-specific metrics to CloudWatch under the `AWS/Bedrock/AgentCore` namespace:

| Metric | Description |
|---|---|
| `InputTokens` | Input tokens per LLM call |
| `OutputTokens` | Output tokens per LLM call |
| `Latency` | End-to-end invocation latency |
| `ToolCallCount` | Number of tool calls per invocation |
| `ErrorCount` | Number of failed invocations |
| `GoalSuccessRate` | Online evaluation score (when configured) |

Use these metrics to build CloudWatch dashboards for latency percentiles, token volume, and error rate alerting. They are compatible with AWS Cost Anomaly Detection and CloudWatch Anomaly Detection.

## CloudWatch Transaction Search

Transaction Search lets you filter and drill into individual traces by agent name, session ID, or custom trace attributes without writing CloudWatch Insights queries.

**Setup**: The platform Terraform observability sub-module enables Transaction Search automatically. It creates the required IAM resource policy via `enable_transaction_search = true`.

**Viewing traces**:

1. CloudWatch console → GenAI Observability → Bedrock AgentCore
2. Transaction Search → filter by agent name or session ID
3. Trace timeline: Agent invocation → LLM calls → Tool calls → Memory ops → Response

## CloudWatch Vended Logs

The agents Terraform module creates a CloudWatch log group per agent at `/aws/bedrock-agentcore/runtimes/{agent-id}` and wires it via the CloudWatch Vended Logs delivery API:

- `aws_cloudwatch_log_delivery_source` — the AgentCore Runtime as log source
- `aws_cloudwatch_log_delivery_destination` — the per-agent log group
- `aws_cloudwatch_log_delivery` — the delivery configuration

Container startup errors, runtime exceptions, and application logs appear here automatically. No `logging_configuration` block is needed on the `aws_bedrockagentcore_agent_runtime` resource — the vended logs delivery API is the correct mechanism.

### CloudWatch Data Protection (log masking)

Layer 2 data protection masks PII patterns in log streams at rest, independently of any in-process guardrail. It is active when `cloudwatch_masking_identifiers` is non-empty in the blueprint:

```yaml
observability:
  data_protection:
    cloudwatch_masking_identifiers:
      - EmailAddress
      - CreditCardNumber
      - USPhoneNumber
      - USSocialSecurityNumber
```

This creates a CloudWatch Data Protection policy that masks matched patterns before they are stored — even if PII reaches the log stream, it is redacted at the storage layer. This operates regardless of whether `data_protection.provider` is `bedrock`, `presidio`, or `none`. The two layers are independent: in-process (Layer 1) reduces PII at the source; CloudWatch masking (Layer 2) catches residual leakage.

Available identifiers follow the [CloudWatch Logs Data Protection](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/mask-sensitive-log-data-types.html) naming convention.

## See also

- [Langfuse](langfuse) — session-level traces and prompt debugging alongside CloudWatch
- [Data protection](data-protection) — in-process PII filtering (Bedrock Guardrails, Presidio)
- [Observability overview](observability) — session baggage, custom spans, OTEL flush behavior
