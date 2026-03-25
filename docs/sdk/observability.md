---
title: Observability
nav_order: 6
parent: SDK Reference
---

# Observability

The Observability subsystem provides full-stack instrumentation for agent workloads. It integrates AWS X-Ray, CloudWatch GenAI metrics, Langfuse experiment tracking, structured logging, audit logging, cost tracking, and alerting — all configurable from the blueprint.

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

OTEL is configured via environment variables, not programmatic initialization. The `config_gen.py` module generates the required env vars from blueprint configuration, and the generated Dockerfile wraps the entrypoint with `opentelemetry-instrument`:

```dockerfile
# Generated Dockerfile (when runtime.observability_enabled: true)
RUN pip install --no-cache-dir aws-opentelemetry-distro
CMD ["opentelemetry-instrument", "python", "-m", "app"]
```

The `generate_otel_env()` function produces the env vars that configure the AWS OpenTelemetry distro:

```python
from agent_core.runtime.config_gen import generate_otel_env

env_vars = generate_otel_env(blueprint)
# Returns:
# {
#   "OTEL_PYTHON_DISTRO": "aws_distro",
#   "OTEL_PYTHON_CONFIGURATOR": "aws_configurator",
#   "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
#   "OTEL_TRACES_EXPORTER": "otlp",
#   "OTEL_EXPORTER_OTLP_LOGS_HEADERS": "x-aws-log-group=...,x-aws-log-stream=default,...",
#   "OTEL_RESOURCE_ATTRIBUTES": "service.name=my-agent",
#   "AGENT_OBSERVABILITY_ENABLED": "true",
# }
```

These env vars are set in the container task definition. When deployed via Terraform, the `modules/agents/runtime.tf` module injects these env vars automatically when `observability_enabled = true` (the default). The values mirror the exact output of `generate_otel_env()`.

> **Runtime Logging:** Terraform also creates a CloudWatch log group per agent at `/aws/bedrock-agentcore/runtimes/{agent-id}` and wires it via the CloudWatch Vended Logs delivery API (`aws_cloudwatch_log_delivery_source` + `aws_cloudwatch_log_delivery_destination` + `aws_cloudwatch_log_delivery`). This replaces the missing `logging_configuration` block on the `aws_bedrockagentcore_agent_runtime` resource. No `configure_otel()` function call is needed — the `opentelemetry-instrument` CLI wrapper handles initialization at process start.

Traces are exported to AWS X-Ray via the OTEL exporter. Spans include:

- Agent invocation start/end
- Each tool call with input/output sizes
- Bedrock model calls with token counts
- Memory read/write operations

## Session Baggage

`set_session_baggage` from `agent_core.observability.otel` attaches session and user IDs to OTEL baggage, so every downstream span and log inherits these values for session-level filtering:

```python
from agent_core.observability.otel import set_session_baggage, detach_session_baggage

token = set_session_baggage(session_id="sess-001", user_id="user-123")
try:
    # All spans created here inherit session.id and user.id
    result = agent(prompt)
finally:
    detach_session_baggage(token)
```

## Custom Spans

`get_agent_tracer` returns an OTEL tracer scoped to an agent, for creating custom spans inside tool functions:

```python
from agent_core.observability.otel import get_agent_tracer

tracer = get_agent_tracer("my-agent")

@tool
def search(query: str) -> str:
    with tracer.start_as_current_span("search") as span:
        span.set_attribute("search.query", query)
        return do_search(query)
```

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

## Data Protection

Data protection is handled via Amazon Bedrock Guardrails, configured at the infrastructure layer. Guardrails intercept model inputs and outputs to apply PII masking, content filtering, and topic restrictions before content reaches any storage backend. Configure guardrails in the blueprint and they are attached to the agent's Bedrock model calls automatically.

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
  alerts:
    enabled: true
    sns_topic_arn: "arn:aws:sns:${AWS_REGION}:${AWS_ACCOUNT_ID}:agent-alerts"
    cost_threshold_usd: 1.00
```
