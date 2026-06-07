---
title: Observability
nav_order: 6
parent: SDK Reference
---

# Observability

The Observability subsystem provides full-stack instrumentation for agent workloads. It integrates OTEL/X-Ray distributed tracing, CloudWatch GenAI metrics, Langfuse experiment tracking, structured logging, DynamoDB audit logging, cost tracking, and PII data protection — all configurable from the blueprint.

> **Architecture guide:** [Observability & Evaluation](../observability.md)

## Key Classes and Functions

| Class / Function | Module | Purpose |
|-----------------|--------|---------|
| `create_observability_hooks()` | `agent_core.hooks.observability_hooks` | Factory — builds and returns a `CompositeObservabilityHook` |
| `CompositeObservabilityHook` | `agent_core.hooks.observability_hooks` | Composes `LangfuseHook` + `CostTracker` + `AuditLogWriter` into one Strands hook |
| `LangfuseHook` | `agent_core.observability.langfuse_hook` | Strands hook — exports session traces and tool spans to Langfuse |
| `AuditLogWriter` | `agent_core.observability.audit_log` | Writes structured audit events to DynamoDB |
| `CostTracker` | `agent_core.observability.cost_tracker` | Tracks token consumption and estimated cost per invocation |
| `StructuredLogger` | `agent_core.observability.structured_logger` | JSON-structured logger with automatic context enrichment |

## `create_observability_hooks()`

The standard way to build the observability hook stack in agent code:

```python
from agent_core.hooks.observability_hooks import create_observability_hooks

obs_hook = create_observability_hooks(
    agent_id="my-agent",
    prompt_id="my-prompt",
    prompt_version="v3",
    execution_mode="production",
)

agent = Agent(model=model, tools=tools, hooks=[obs_hook])
```

Returns a `CompositeObservabilityHook`. All env vars (`LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_ENABLED`) are read inside the function. Setting `LANGFUSE_ENABLED=false` disables Langfuse without changing the blueprint (useful for local dev).

`BlueprintLoader` calls this automatically when `observability.enabled: true` is set in the blueprint.

## `LangfuseHook`

`LangfuseHook` is a dataclass (not a class with `from_blueprint()`). Construct directly or via `create_observability_hooks()`:

```python
from agent_core.observability.langfuse_hook import LangfuseHook

hook = LangfuseHook(
    agent_id="my-agent",
    prompt_id="my-prompt",
    prompt_version="v3",
    execution_mode="production",
)
```

Each agent run creates a Langfuse trace. After commit `8f8b367`, the full conversation — prompt messages, model reasoning, tool calls, and tool results — is serialized as JSON and sent to Langfuse trace input/output. Token aggregates, tool spans, and evaluation scores are also attached.

> **Double-trace architecture:** When using LiteLLM, the LiteLLM proxy writes per-generation spans to Langfuse via `success_callback: langfuse`, while `LangfuseHook` writes session-level traces. Both run simultaneously and capture different granularities — per-generation token counts versus full session context. This is intentional; expect to see both trace types in your Langfuse project.

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | `str` | Identifier for the agent (becomes Langfuse session name) |
| `prompt_id` | `str` | Prompt name for Langfuse metadata |
| `prompt_version` | `str` | Prompt version for Langfuse metadata |
| `execution_mode` | `str` | Execution mode (`simulation`, `staging`, `production`) |

## `AuditLogWriter`

Writes structured audit events to a DynamoDB table (not CloudWatch Logs):

```python
from agent_core.observability.audit_log import AuditLogWriter

audit = AuditLogWriter(table_name=os.environ["AUDIT_LOG_TABLE"])

audit.log(
    event_type="tool_invoked",
    agent_id="my-agent",
    payload={
        "tool": "send_email",
        "user_id": "u-123",
        "parameters_hash": hash_sensitive(params),
    },
)
```

The `log()` method is synchronous. `table_name` defaults to `os.getenv("AUDIT_TABLE", "audit_log")` when constructed without an explicit argument; the blueprint wires the correct table name via the `table_env` field in `observability.audit_log`.

Sensitive parameter values should never be written to audit logs. Use a hash or redacted representation.

## `CostTracker`

Tracks token consumption and estimates USD cost per invocation:

```python
from agent_core.observability.cost_tracker import CostTracker

tracker = CostTracker()

input_usd, output_usd = tracker.get_pricing("claude-sonnet-4-6")
cost = tracker.compute_cost(
    model_id="claude-sonnet-4-6",
    input_tokens=1000,
    output_tokens=500,
)
```

Pricing resolution order (first match wins):

1. `custom_pricing` constructor parameter
2. `MODEL_PRICING` env var — JSON object mapping model ID to `[input_per_1k, output_per_1k]` (fallback: `BEDROCK_MODEL_PRICING`)
3. Built-in defaults (see below)
4. `default_pricing` constructor parameter
5. `MODEL_DEFAULT_PRICING` env var — JSON array `[input_per_1k, output_per_1k]` (fallback: `BEDROCK_DEFAULT_PRICING`)
6. Returns `(0.0, 0.0)` with a logged warning — never raises

**Built-in defaults** (zero-config cost tracking for these model IDs):

| Model ID | Input $/1k tokens | Output $/1k tokens |
|----------|------------------|--------------------|
| `claude-sonnet-4-6` | $0.003 | $0.015 |
| `claude-haiku-4-5` | $0.00025 | $0.00125 |
| `openai/claude-sonnet-4-6` | $0.003 | $0.015 |
| `openai/claude-haiku-4-5` | $0.00025 | $0.00125 |

The `openai/` prefixed variants match LiteLLM's internal model IDs when `custom_llm_provider="openai"` is set.

## OTEL Auto-Instrumentation

OTEL is configured via environment variables generated by `agent_core.runtime.config_gen.generate_otel_env()`. The Terraform `modules/agents/runtime.tf` injects these automatically when `observability_enabled = true`. No application-level `configure_otel()` call is needed.

```python
from agent_core.runtime.config_gen import generate_otel_env

env_vars = generate_otel_env(blueprint)
# Returns OTEL_PYTHON_DISTRO, OTEL_PYTHON_CONFIGURATOR,
# OTEL_EXPORTER_OTLP_PROTOCOL, OTEL_TRACES_EXPORTER,
# OTEL_EXPORTER_OTLP_LOGS_HEADERS, OTEL_RESOURCE_ATTRIBUTES, etc.
```

## Session Baggage

`set_session_baggage` attaches session and user IDs to OTEL baggage so every downstream span inherits them:

```python
from agent_core.observability.otel import set_session_baggage, detach_session_baggage

token = set_session_baggage(session_id="sess-001", user_id="user-123")
try:
    result = agent(prompt)
finally:
    detach_session_baggage(token)
```

## Custom Spans

```python
from agent_core.observability.otel import get_agent_tracer

tracer = get_agent_tracer("my-agent")

@tool
def search(query: str) -> str:
    with tracer.start_as_current_span("search") as span:
        span.set_attribute("search.query", query)
        return do_search(query)
```

## Data Protection

The platform offers two in-process PII filtering options, controlled by `observability.data_protection.provider` in the blueprint:

| `provider` | Mechanism | Requirements |
|------------|-----------|--------------|
| `bedrock` | Bedrock Guardrails API — intercepts model I/O | `model.provider: bedrock` AND `BEDROCK_GUARDRAIL_ID` env var set |
| `presidio` | Microsoft Presidio — local text redaction | `pip install 'agent-core[presidio]'`; works with any inference provider |
| `none` | No in-process PII filter | — |

CloudWatch Data Protection (Layer 2) is independent — it masks PII in CloudWatch log streams when `cloudwatch_masking_identifiers` is non-empty, regardless of which `provider` is selected.

See [Observability & Evaluation — Data Protection](../observability/data-protection.md) for full configuration details.

## Blueprint Configuration

The real `ObservabilityConfig` schema fields:

```yaml
observability:
  enabled: true                         # Master toggle for all app-level hooks

  trace_attributes:                     # Custom OTEL resource attributes
    team: platform
    service_tier: critical

  langfuse:
    enabled: true
    public_key_env: LANGFUSE_PUBLIC_KEY  # Name of the env var holding the key
    secret_key_env: LANGFUSE_SECRET_KEY
    host_env: LANGFUSE_HOST
    tags:
      environment: production

  audit_log:
    enabled: true
    table_env: AUDIT_LOG_TABLE           # Env var name for the DynamoDB table name
    ttl_days: 1825                       # ~5 years

  dashboard:
    metric_namespace: "/Agents/MyAgent"
    log_group_prefix: "/agents/my-agent"

  data_protection:
    provider: presidio                   # bedrock | presidio | none
    presidio_entities: [EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD]
    presidio_language: en
    cloudwatch_masking_identifiers:      # Layer 2 — always-on in CloudWatch
      - EMAIL_ADDRESS
      - SSN
```

## See Also

- [Observability & Evaluation guide](../observability.md) — Architecture, Langfuse setup, double-trace explanation
- [Evaluation SDK reference](evaluation.md) — Built-in evaluators, custom LLM-as-judge
