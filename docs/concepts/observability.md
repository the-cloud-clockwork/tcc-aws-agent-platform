---
title: Observability
nav_order: 5
---

# Tracing Agent Behavior

AgentCore Observability captures the complete execution trace of every agent invocation — every LLM call, every tool call, every error — and publishes them to CloudWatch with semantic GenAI metrics. It is the foundation for debugging, performance tuning, and evaluation.

## What Gets Traced

A single agent invocation produces a full execution tree:

```
Trace: session_abc / invocation_1
+-- Agent Invocation (2.3s total)
|   +-- LLM Call #1 (0.8s)
|   |   +-- Prompt tokens: 142
|   |   +-- Completion tokens: 67
|   |   +-- Tool decision: search_documents(query="...")
|   +-- Tool Call: search_documents (0.1s)
|   |   +-- Input: {query: "..."}
|   |   +-- Output: [3 documents]
|   +-- LLM Call #2 (0.6s)
|   |   +-- Prompt tokens: 203
|   |   +-- Final response
|   +-- Response delivered to user
```

Every LLM call records: model ID, full prompt, full response, input/output token counts, latency. Every tool call records: tool name, parameters, result, latency. Errors record: exception type, stack trace, which step failed.

## How to Enable — Zero Code for Runtime

On AgentCore Runtime, observability is automatic. Add the OTEL distro to your container and wrap the entrypoint:

```dockerfile
RUN pip install aws-opentelemetry-distro
CMD ["opentelemetry-instrument", "python", "-m", "agent_core.runtime.entrypoint"]
```

No code changes. The OTEL auto-instrumentation hooks into Strands' internal execution graph and exports traces to CloudWatch. You get the full trace for every invocation without touching your agent logic.

## Custom Spans

When you want to trace your own tool internals — database queries, external API calls, multi-step computations — add custom spans:

```python
from opentelemetry import trace

tracer = trace.get_tracer("my_tools", "1.0.0")

@tool
def complex_search(query: str) -> str:
    with tracer.start_as_current_span("database_search") as span:
        span.set_attribute("search.query", query)
        results = db.search(query)
        span.set_attribute("search.results_count", len(results))
        span.add_event("search_completed")
        return json.dumps(results)
```

Custom spans appear as children of the tool call span in the trace tree.

## Session Correlation

To correlate traces across multiple invocations for the same user session, attach baggage at invocation time:

```python
from opentelemetry import baggage, context

ctx = baggage.set_baggage("session.id", user_session_id)
ctx = baggage.set_baggage("user.id", user_id)
token = context.attach(ctx)
result = await agent.invoke(prompt)
context.detach(token)
```

Traces emitted during the attached context carry these values, making it easy to filter all spans for a specific user session in CloudWatch Insights.

## Strands trace_attributes

Strands has native OTEL integration. Attach metadata at the agent level via `trace_attributes`, and every span the agent produces carries these values:

```python
agent = Agent(
    model=model,
    tools=[...],
    trace_attributes={
        "user.id": user_id,
        "environment": "production",
        "agent.version": "2.1.0",
    },
)
```

Declare `trace_attributes` in the blueprint to apply them automatically:

```yaml
observability:
  trace_attributes:
    environment: production
    agent.version: "2.1.0"
```

## CloudWatch GenAI Metrics

AgentCore publishes GenAI-specific metrics to CloudWatch Metrics under the `AWS/Bedrock/AgentCore` namespace:

| Metric | Description |
|--------|-------------|
| `InputTokens` | Input tokens per LLM call |
| `OutputTokens` | Output tokens per LLM call |
| `Latency` | End-to-end invocation latency |
| `ToolCallCount` | Number of tool calls per invocation |
| `ErrorCount` | Number of failed invocations |
| `GoalSuccessRate` | Online evaluation score (when configured) |

Use these metrics to build CloudWatch dashboards for latency percentiles, token cost tracking, and error rate alerting.

## Langfuse Integration

For teams using Langfuse for LLM observability, `agent-core` provides a pre-built `LangfuseHook`:

```yaml
observability:
  langfuse:
    enabled: true
    public_key: ${LANGFUSE_PUBLIC_KEY}
    secret_key: ${LANGFUSE_SECRET_KEY}
    host: ${LANGFUSE_HOST}
```

The hook sends traces to Langfuse alongside CloudWatch. Both streams are active simultaneously — CloudWatch for infrastructure alerting, Langfuse for prompt debugging and cost analysis.

## Data Protection

Two mechanisms prevent sensitive data from appearing in traces:

**Bedrock Guardrails** — anonymize PII in agent responses before they reach the trace:

```yaml
model:
  provider: bedrock
  model_id: ${MODEL_ID}
  guardrail_id: ${GUARDRAIL_ID}
  guardrail_version: "1"
  guardrail_trace: enabled
```

> **SDK note:** In the Strands SDK, guardrails are configured directly on the model: `BedrockModel(model_id=..., guardrail_id="abc123", guardrail_version="1")`. The blueprint `model:` block maps to these parameters automatically.

**CloudWatch Logs Data Protection** — apply data protection policies to log groups to mask PII patterns (SSNs, credit card numbers, email addresses) at rest. This operates independently of guardrails — even if PII makes it into a trace event, it is masked before being stored.

Together these two layers provide defense in depth: guardrails reduce PII at the source, data protection masks residual leakage at the storage layer.

## Audit Logging

`AuditLogWriter` writes structured audit events to a dedicated CloudWatch log group. Audit events include:

- Session start and end
- Tool calls with parameters (after PII masking)
- Policy decisions (allow/deny)
- Identity token validations
- Memory read and write operations

Audit logs are separate from trace logs, retained for compliance, and can be forwarded to a SIEM.

```yaml
observability:
  audit_logging:
    enabled: true
    log_group: ${AUDIT_LOG_GROUP}
    retention_days: 90
```

## Blueprint Configuration

```yaml
observability:
  enabled: true
  trace_attributes:
    environment: production
  langfuse:
    enabled: false
  audit_logging:
    enabled: true
    log_group: ${AUDIT_LOG_GROUP}
```

## See Also

- [Evaluation Concepts](evaluation) — how evaluation reads OTEL traces to score agent behavior
- [Observability SDK Reference](../sdk/) — `LangfuseHook`, `AuditLogWriter`, `XRayTracer`, `CostTracker`
- [Agent Blueprint](../blueprints/agent-blueprint) — `observability:` block reference
