---
title: Observability
nav_order: 6
---

# Observability

The Observability subsystem provides full-stack instrumentation for agent workloads. It integrates AWS X-Ray, CloudWatch GenAI metrics, Langfuse experiment tracking, structured logging, audit logging, cost tracking, PII masking, and alerting — all configurable from the blueprint.

## Key Classes

| Class | Purpose |
|-------|---------|
| `LangfuseHook` | Strands hook — exports traces and evaluations to Langfuse |
| `AuditLogWriter` | Writes structured audit events to CloudWatch Logs |
| `XRayTracer` | Propagates X-Ray trace context across agent invocations |
| `CostTracker` | Tracks token consumption and estimated cost per invocation |
| `StructuredLogger` | JSON-structured logger with automatic context enrichment |
| `AlertPublisher` | Publishes alerts to SNS when configurable thresholds are breached |
| `CompositeObservabilityHook` | Composes multiple hooks into a single Strands hook |

## OTEL Auto-Instrumentation

The runtime configures OpenTelemetry automatically when `observability.otel` is enabled. OTEL instruments the Strands agent loop, HTTP clients, and AWS SDK calls with no additional code:

```python
from agent_core.observability.otel import configure_otel

# Called once at app startup (AgentCoreApp.from_blueprint does this automatically)
configure_otel(service_name="my-agent", endpoint="${OTEL_EXPORTER_ENDPOINT}")
```

Traces are exported to AWS X-Ray via the OTEL → X-Ray exporter. Spans include:

- Agent invocation start/end
- Each tool call with input/output sizes
- Bedrock model calls with token counts
- Memory read/write operations

## X-Ray Tracing

`XRayTracer` adds subsegments and propagates the trace ID across async boundaries:

```python
from agent_core.observability import XRayTracer

tracer = XRayTracer.from_blueprint("agent.yaml")

@tracer.trace("process-document")
async def process(doc_id: str):
    # This function is wrapped in an X-Ray subsegment
    ...
```

The `trace_attributes` decorator attaches custom metadata to the current segment:

```python
from agent_core.observability.xray_tracing import trace_attributes

@trace_attributes({"doc.type": "invoice", "doc.size_kb": 42})
async def analyze_document(doc):
    ...
```

## CloudWatch GenAI Metrics

`CostTracker` publishes standard CloudWatch GenAI metrics for every Bedrock model call:

| Metric | Description |
|--------|-------------|
| `InputTokenCount` | Prompt tokens per invocation |
| `OutputTokenCount` | Completion tokens per invocation |
| `InvocationLatency` | End-to-end latency in milliseconds |
| `EstimatedCost` | Estimated USD cost based on published pricing |

These metrics appear in the `/AWS/Bedrock/AgentCore` namespace and are compatible with AWS Cost Anomaly Detection.

## Langfuse Integration

`LangfuseHook` is a Strands hook that exports full trace data to Langfuse for experiment tracking and prompt evaluation:

```python
from agent_core.observability import LangfuseHook

langfuse_hook = LangfuseHook.from_blueprint("agent.yaml")

agent = Agent(
    model=model,
    tools=tools,
    hooks=[langfuse_hook],
)
```

Each agent run creates a Langfuse trace with spans for every tool call, model invocation, and memory operation. Evaluation scores from the [Evaluation subsystem](evaluation.md) are attached to the trace automatically.

## Audit Logging

`AuditLogWriter` writes tamper-evident audit events to a dedicated CloudWatch Log Group:

```python
from agent_core.observability import AuditLogWriter

audit = AuditLogWriter.from_blueprint("agent.yaml")

await audit.write({
    "event": "tool_invoked",
    "tool": "send_email",
    "user_id": "u-123",
    "parameters_hash": hash_sensitive(params),
})
```

Sensitive parameter values are never written to audit logs. Use `parameters_hash` to log a fingerprint for correlation without exposing content.

## Data Protection (PII Masking)

`DataProtection` intercepts log and audit writes and masks PII patterns before they reach any storage backend:

```python
from agent_core.observability.data_protection import DataProtection

protection = DataProtection(patterns=["email", "phone", "credit_card"])

# Automatically applied when configured in blueprint
masked = protection.mask("Contact me at user@example.com or 555-0100")
# Output: "Contact me at [EMAIL] or [PHONE]"
```

Blueprint configuration:

```yaml
observability:
  data_protection:
    enabled: true
    patterns: ["email", "phone", "ssn", "credit_card"]
```

## CompositeObservabilityHook

Combine multiple hooks into one to keep the agent constructor clean:

```python
from agent_core.observability import CompositeObservabilityHook

obs_hook = CompositeObservabilityHook.from_blueprint("agent.yaml")
# Internally composes: LangfuseHook + XRayTracer + CostTracker hooks

agent = Agent(model=model, tools=tools, hooks=[obs_hook])
```

## Blueprint Configuration

```yaml
observability:
  xray: true
  otel: true
  langfuse:
    enabled: true
    public_key_secret: "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:langfuse-public-key"
    secret_key_secret: "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:langfuse-secret-key"
    host: "https://cloud.langfuse.com"
  audit_log:
    enabled: true
    log_group: "/agents/my-agent/audit"
  data_protection:
    enabled: true
    patterns: ["email", "phone"]
  alerts:
    enabled: true
    sns_topic_arn: "arn:aws:sns:${AWS_REGION}:${AWS_ACCOUNT_ID}:agent-alerts"
    cost_threshold_usd: 1.00
```
