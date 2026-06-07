---
title: Langfuse Integration
nav_order: 3
parent: "Observability & Evaluation"
---

# Langfuse Integration

The platform provides a pre-built `LangfuseHook` that exports full trace data to Langfuse for prompt debugging, cost analysis, and experiment tracking. Langfuse runs alongside CloudWatch — both streams are active simultaneously by design.

## Blueprint configuration

```yaml
observability:
  langfuse:
    enabled: true
    public_key_env: LANGFUSE_PUBLIC_KEY   # name of the env var, not the value
    secret_key_env: LANGFUSE_SECRET_KEY
    host_env: LANGFUSE_HOST
    tags: []                              # static tags on every trace
```

The `public_key_env`, `secret_key_env`, and `host_env` fields hold the **names** of environment variables, not credential values. The actual secrets are injected at runtime via the Terraform agents module. Never write credentials directly in blueprint YAML.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `LANGFUSE_HOST` | Yes | Langfuse instance URL (e.g. `https://cloud.langfuse.com`) |
| `LANGFUSE_PUBLIC_KEY` | Yes | Langfuse project public key |
| `LANGFUSE_SECRET_KEY` | Yes | Langfuse project secret key |
| `LANGFUSE_ENABLED` | No | Set to `false` to disable without changing the blueprint |

`LANGFUSE_ENABLED=false` is the escape hatch for local development — it disables Langfuse tracing without touching the blueprint, useful when running agents locally without a Langfuse instance.

If `LANGFUSE_HOST` is absent the hook silently no-ops rather than crashing. The agent continues running; Langfuse traces simply are not emitted.

## How LangfuseHook works

`LangfuseHook` is a plain dataclass that implements the Strands callback protocol. It is not instantiated directly by application code — `BlueprintLoader` composes it into `CompositeObservabilityHook` via `create_observability_hooks()`:

```python
from agent_core.hooks.observability_hooks import create_observability_hooks

hook = create_observability_hooks(
    agent_id="my-agent",
    prompt_id="my-agent-prompt",
    prompt_version="v1.2",
    execution_mode="production",
)
agent = Agent(model=model, tools=tools, hooks=[hook])
```

`CompositeObservabilityHook` implements the Strands `HookProvider` protocol via `register_hooks()`. It registers typed event callbacks:

| Strands event | Hook action |
|---|---|
| `BeforeInvocationEvent` | Creates a Langfuse trace; resets token counters |
| `AfterModelCallEvent` | Increments cycle counter; captures stop reason |
| `AfterToolCallEvent` | Logs tool call to `StructuredLogger`; increments error counter on failure |
| `AfterInvocationEvent` | Reads aggregated token usage from `event_loop_metrics`; emits Langfuse generation span; finalizes and flushes the trace; writes audit record |

## Full conversation capture

Langfuse traces include the complete conversation — not just token counts. The `_on_after_invocation` handler reads `agent.messages` from the `AfterInvocationEvent` and serializes the full conversation (prompt, intermediate reasoning, tool calls, tool results, final answer) as JSON before sending it to Langfuse.

This was introduced to fix a gap where trace `input`/`output` fields were `null` — only token metadata was recorded. The fix extracts:

- **Prompt** — first user message's text blocks
- **Full conversation** — all messages in Strands' native format (capped at 200,000 characters), sent as the generation `input`
- **Final output** — last assistant message's text blocks, sent as the generation `output`

**PII implication**: full conversation content reaches Langfuse. If your prompts or tool outputs contain PII, configure a `pii_filter` via `data_protection.provider: bedrock` or `data_protection.provider: presidio`. The `pii_filter` callable is applied to input and output text before they are sent to Langfuse. See [Data protection](data-protection) for the complete setup.

## Double-trace design

When using LiteLLM as the inference provider, Langfuse receives traces from two independent sources simultaneously:

| Source | What it captures | Granularity |
|---|---|---|
| LiteLLM proxy `success_callback: langfuse` | Per-generation spans — individual model calls with latency and token counts as seen by the proxy | Generation (per LLM call) |
| `LangfuseHook` in `CompositeObservabilityHook` | Session-level traces — aggregated token totals, tool call sequence, full conversation JSON, estimated cost | Session (full invocation) |

This is intentional. The two streams capture different granularities and serve different purposes:

- **LiteLLM traces** reveal proxy-level latency, model routing decisions, and per-request token counts as seen by the proxy. Useful for diagnosing slow calls, routing issues, or cost by model.
- **Hook traces** reveal agent behavior — what the agent decided, which tools it called, in what order, and what the final output was. Useful for prompt debugging and quality evaluation.

Expect to see two trace entries per invocation in Langfuse when both are configured. They share a `session_id` for correlation. Filter by `agent_id` metadata to view only the agent-level session traces.

## Trace metadata

Every Langfuse trace carries these structured metadata tags:

| Tag | Value |
|---|---|
| `agent_id` | Blueprint `id` field |
| `prompt_id` | Blueprint `prompt_ref` field |
| `prompt_version` | Blueprint `version` field |
| `execution_mode` | `simulation`, `staging`, or `production` |
| `target` | Target entity (when provided by the invocation handler) |

Use these tags to filter traces by agent, execution mode, or prompt version in the Langfuse UI.

## Langfuse and evaluation

When `evaluation.provider: langfuse` is set in the blueprint, evaluation scores are attached to the Langfuse trace via `langfuse.score()`. See [Evaluation](evaluation) for the full Langfuse evaluation provider details.

## See also

- [Data protection](data-protection) — configure `pii_filter` to sanitize content before it reaches Langfuse
- [Cost tracking](cost-tracking) — `CostTracker` runs inside `LangfuseHook` and adds `cost_usd` to every generation span
- [Evaluation](evaluation) — `evaluation.provider: langfuse` attaches scores to Langfuse traces
- [AWS-native](aws-native) — CloudWatch-side traces that run in parallel with Langfuse
