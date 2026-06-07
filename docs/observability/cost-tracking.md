---
title: Cost Tracking
nav_order: 4
parent: "Observability & Evaluation"
---

# Cost Tracking

`CostTracker` computes USD cost for every model invocation based on token counts and a configurable pricing table. It runs inside `LangfuseHook` as part of `CompositeObservabilityHook` — cost data appears automatically on every Langfuse generation span without any additional configuration.

## How it works

After each model call, `LangfuseHook.after_model_invocation()` calls `CostTracker.compute_cost(model_id, input_tokens, output_tokens)`. The result is attached to the Langfuse generation span as `cost_usd` metadata and accumulated across all LLM cycles in the invocation. The final session trace includes `total_cost_usd` in its metadata.

## Built-in pricing defaults

`CostTracker` ships with built-in pricing for the models most commonly used through a LiteLLM proxy. Cost tracking works out of the box for these model IDs with no configuration:

| Model ID | Input (USD / 1k tokens) | Output (USD / 1k tokens) |
|---|---|---|
| `claude-sonnet-4-6` | $0.003 | $0.015 |
| `claude-haiku-4-5` | $0.00025 | $0.00125 |
| `openai/claude-sonnet-4-6` | $0.003 | $0.015 |
| `openai/claude-haiku-4-5` | $0.00025 | $0.00125 |

The `openai/` prefixed variants exist because `LiteLLMModel` with `custom_llm_provider='openai'` exposes the model ID in that form on the generation event. Both forms map to the same pricing.

Indicative pricing — verify current rates with your provider. Override with `MODEL_PRICING` if your proxy negotiates different rates.

## Pricing configuration

### Override with MODEL_PRICING

Set `MODEL_PRICING` to a JSON object mapping model IDs to `[input_per_1k, output_per_1k]` tuples. Custom entries merge on top of built-in defaults — known model IDs are still resolved if not overridden:

```bash
# In your container environment (injected by Terraform or set manually)
MODEL_PRICING='{"my-custom-model": [0.001, 0.005], "gpt-5-codex": [0.002, 0.010]}'
```

Or in Terraform via `extra_environment_variables`:

```hcl
extra_environment_variables = {
  MODEL_PRICING = jsonencode({
    "my-custom-model" = [0.001, 0.005]
  })
}
```

### Fallback pricing for unknown models

Set `MODEL_DEFAULT_PRICING` to a JSON array `[input_per_1k, output_per_1k]` to apply a fallback rate to any model not explicitly listed:

```bash
MODEL_DEFAULT_PRICING='[0.001, 0.003]'
```

Without `MODEL_DEFAULT_PRICING`, an unknown model logs a warning and returns `(0.0, 0.0)` — cost tracking is disabled for that model but the agent continues running.

### Deprecated aliases

The legacy env vars `BEDROCK_MODEL_PRICING` and `BEDROCK_DEFAULT_PRICING` are accepted as aliases for backward compatibility with Bedrock-only deployments. A warning is logged when they are used. Migrate to `MODEL_PRICING` and `MODEL_DEFAULT_PRICING` for provider-agnostic deployments.

## Pricing resolution order

`CostTracker.get_pricing(model_id)` resolves pricing in this order:

1. `custom_pricing` constructor parameter (for programmatic override)
2. `MODEL_PRICING` env var (falls back to `BEDROCK_MODEL_PRICING` if absent)
3. Built-in defaults (the four model IDs listed above)
4. `default_pricing` constructor parameter
5. `MODEL_DEFAULT_PRICING` env var (falls back to `BEDROCK_DEFAULT_PRICING` if absent)
6. Returns `(0.0, 0.0)` and logs a warning — never crashes

## Direct use

`CostTracker` is available as a standalone class for use outside the hook system:

```python
from agent_core.observability.cost_tracker import CostTracker

tracker = CostTracker()

cost = tracker.compute_cost(
    model_id="claude-sonnet-4-6",
    input_tokens=1500,
    output_tokens=800,
)
print(f"Total cost: ${cost.total_usd:.6f}")
print(f"  Input:  ${cost.input_cost_usd:.6f}")
print(f"  Output: ${cost.output_cost_usd:.6f}")

# List all models with known pricing
print(tracker.known_models)
```

The `TokenCost` return value is a frozen dataclass with fields: `model_id`, `input_tokens`, `output_tokens`, `input_cost_usd`, `output_cost_usd`, `total_usd`. Call `.to_dict()` to get a JSON-serializable form.

## CloudWatch cost metrics

`CostTracker` feeds cost data into Langfuse generation spans. For CloudWatch-side cost visibility, use the built-in `EstimatedCost` metric published by the observability hooks under the `AgentPlatform` namespace (configurable via `dashboard.metric_namespace` in the blueprint).

## See also

- [Langfuse](langfuse) — `cost_usd` appears on every Langfuse generation span
- [AWS-native](aws-native) — CloudWatch cost metrics
- [Inference Providers](../inference) — model ID formatting differences between providers affect which pricing key is matched
