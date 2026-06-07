---
title: Observability Overview
nav_order: 1
parent: "Observability & Evaluation"
---

# Observability Overview

The platform captures the complete execution trace of every agent invocation — every LLM call, every tool call, every error — and publishes them via OpenTelemetry. You can route these traces to AWS CloudWatch, Langfuse, or both simultaneously.

## What gets traced

A single agent invocation produces a full execution tree:

```
Trace: session_abc / invocation_1
+-- Agent Invocation (2.3 s total)
|   +-- LLM Call #1 (0.8 s)
|   |   +-- Prompt tokens: 142
|   |   +-- Completion tokens: 67
|   |   +-- Tool decision: search_documents(query="...")
|   +-- Tool Call: search_documents (0.1 s)
|   |   +-- Input: {query: "..."}
|   |   +-- Output: [3 documents]
|   +-- LLM Call #2 (0.6 s)
|   |   +-- Prompt tokens: 203
|   |   +-- Final response
|   +-- Response delivered to caller
```

Every LLM call records: model ID, input/output token counts, latency, stop reason. Every tool call records: tool name, parameters, result, latency. Errors record: exception type, stack trace, which step failed.

## Blueprint configuration

```yaml
observability:
  enabled: true                          # master toggle for app-level hooks
  trace_attributes:
    environment: production
    agent.version: "1.0.0"
  langfuse:
    enabled: true
    public_key_env: LANGFUSE_PUBLIC_KEY   # env var name, not the value
    secret_key_env: LANGFUSE_SECRET_KEY
    host_env: LANGFUSE_HOST
    tags: []
  audit_log:
    enabled: true
    table_env: AUDIT_LOG_TABLE            # env var holding the DynamoDB table name
    ttl_days: 1825                        # ~5 years
  dashboard:
    metric_namespace: AgentPlatform
    log_group_prefix: "agents/"
  data_protection:
    provider: bedrock                     # bedrock | presidio | none
    guardrail_id_env: BEDROCK_GUARDRAIL_ID
    guardrail_version_env: BEDROCK_GUARDRAIL_VERSION
    cloudwatch_masking_identifiers: []
```

Setting `observability.enabled: false` disables `LangfuseHook`, `AuditLogWriter`, `CostTracker`, and `StructuredLogger` in a single toggle. It does not affect the OTEL auto-instrumentation wrapper — that is controlled by the Terraform `runtime.observability_enabled` variable.

## Session baggage

Attach session and user identifiers to OTEL baggage so every downstream span and log inherits these values for session-level filtering in CloudWatch Insights or Langfuse:

```python
from agent_core.observability.otel import set_session_baggage, detach_session_baggage

token = set_session_baggage(session_id="sess-001", user_id="user-123")
try:
    result = agent(prompt)
finally:
    detach_session_baggage(token)
```

## Custom spans

Add custom spans inside tool functions to trace database queries, external API calls, or multi-step computations:

```python
from agent_core.observability.otel import get_agent_tracer
from strands import tool

tracer = get_agent_tracer("my-agent")

@tool
def search(query: str) -> str:
    with tracer.start_as_current_span("database_search") as span:
        span.set_attribute("search.query", query)
        results = db.search(query)
        span.set_attribute("search.results_count", len(results))
        return str(results)
```

Custom spans appear as children of the tool call span in the trace tree.

## Trace attributes

Declare static metadata in the blueprint to attach key-value pairs to every OTEL span the agent produces:

```yaml
observability:
  trace_attributes:
    environment: production
    agent.version: "2.1.0"
    team: platform
```

These values flow through to CloudWatch Insights and Langfuse trace metadata automatically.

## Audit logging

`AuditLogWriter` records structured audit events to DynamoDB — not CloudWatch Logs. Events include session start/end, tool calls (with parameters after PII masking), policy decisions, identity token validations, and memory operations. Audit records are separate from trace spans, retained for compliance, and can be exported to a SIEM.

The `AuditLogWriter` is instantiated via `create_observability_hooks()` which is called automatically by `BlueprintLoader`. To use it directly:

```python
from agent_core.observability.audit_log import AuditLogWriter

audit = AuditLogWriter(table_name="my_audit_table")
audit.log(
    event_type="TOOL_INVOKED",
    agent_id="my-agent",
    execution_mode="production",
    payload={"tool": "send_email", "parameters_hash": "abc123"},
)
```

The table name defaults to the `AUDIT_TABLE` env var when no `table_name` is passed. Writes are idempotent via DynamoDB conditional expressions — duplicate event IDs are silently ignored.

## Activation checklist

### Prerequisites (one-time per AWS account)

1. **CloudWatch Transaction Search** — the platform Terraform module enables this automatically when the observability sub-module is deployed (`enable_transaction_search = true`).

2. **ADOT dependency** — add to your container's `requirements.txt`:
   ```
   aws-opentelemetry-distro>=0.10.1
   ```

3. **Dockerfile entrypoint** — wrap the process with the OTEL instrument CLI. The SDK's generated Dockerfile handles this automatically when `runtime.observability_enabled: true` (the default).

### OTEL flush behavior

AgentCore Runtime microVMs are suspended immediately after responding. This means background OTel export threads never reach their normal flush interval. The platform's `_wrap_with_flush()` decorator in `AgentCoreApp` force-flushes the OTel logger, meter, and tracer providers in the `finally` block of every handler shape (async generator, coroutine, sync generator, plain sync). Without this flush, metric and log data is lost on suspension while only traces export successfully.

This is handled automatically when agents use `BlueprintLoader.build_entrypoint()` — no application code change is required.

## See also

- [AWS-native](aws-native) — CloudWatch GenAI metrics, Transaction Search, vended logs
- [Langfuse](langfuse) — `LangfuseHook`, double-trace design, conversation capture
- [Cost tracking](cost-tracking) — `CostTracker`, pricing defaults
- [Data protection](data-protection) — Bedrock Guardrails, Microsoft Presidio
- [Evaluation](evaluation) — LLM-as-judge, 12 built-in evaluators
