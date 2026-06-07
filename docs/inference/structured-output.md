---
title: Structured Output
nav_order: 6
parent: Inference Providers
---

# Structured Output

The platform supports enforcing a structured JSON schema on agent responses. When an agent blueprint declares `output_schema`, every invocation produces a response that validates against a Pydantic model — or the call fails with a clear error rather than returning freeform text.

## How it works

Structured output uses the **Strands native forced-tool path** on all four providers. The Strands SDK passes a `structured_output_model` kwarg to the `Agent` constructor, which internally uses a forced tool-call pattern to make the model produce output conforming to the schema.

This is provider-agnostic: the same path works for `bedrock`, `anthropic`, `litellm`, and `vertex`.

## Minimum Strands version

The native forced-tool path requires **`strands-agents>=1.41.0`**. Earlier versions of the Strands SDK had a forced-tool/`finish_reason` incompatibility with OpenAI-compatible providers: when the model returned a `stop_reason: end_turn` signal without invoking the forced tool, Strands raised `StructuredOutputException` on the second retry attempt instead of recovering gracefully. These incompatibilities were resolved in `strands-agents 1.41.0`. The `agent-core` dependency constraint (`strands-agents[otel]>=1.0.0,<2`) satisfies this automatically when installed fresh from a current index — but if you pin or vendor Strands at an older version you will hit these issues.

{: .note }
> Prior to `strands-agents 1.41.0`, a workaround hook called `StructuredOutputEnforcer` (backed by the `instructor` library) was used to handle non-Bedrock providers. That workaround was removed in full when the upstream bugs were resolved. The `structured_output_enforcer.py` file still exists in the codebase as historical reference but is **not wired** by the loader and has no effect.

## Blueprint configuration

Declare `output_schema` at the top level of the agent blueprint:

```yaml
id: extraction-agent
name: Extraction Agent
version: "1.0.0"
prompt_ref: extraction-agent-system-v1

model:
  provider: litellm
  model_id: claude-sonnet-4-6
  temperature: 0.1
  max_tokens: 4096
  base_url: https://your-litellm-proxy.example.com
  api_key_env: LITELLM_API_KEY

output_schema: ExtractionResult   # Name of a Pydantic model in your schema_registry
```

The value of `output_schema` is a string key looked up in the `schema_registry` dict passed to `BlueprintLoader`:

```python
from pydantic import BaseModel
from agent_core.blueprints.loader import BlueprintLoader

class ExtractionResult(BaseModel):
    entities: list[str]
    summary: str
    confidence: float

loader = BlueprintLoader(
    blueprints_dir="blueprints/",
    schema_registry={
        "ExtractionResult": ExtractionResult,
    },
)
```

If `output_schema` is set but `schema_registry` is `None` or does not contain the named key, the loader raises `BlueprintLoadError` at startup.

## Runtime behavior

When `output_schema` is configured:

1. The loader resolves the Pydantic model class from `schema_registry`.
2. The resolved class is passed as `structured_output_model` to the Strands `Agent` constructor.
3. The Strands agent forces the model to produce a JSON response matching the schema's tool-call format.
4. On success, `agent_result.output` is an instance of the Pydantic model.
5. On failure (the model does not conform after retries), the agent raises `StructuredOutputException`.

## Example: full structured output agent

```yaml
id: classifier-agent
name: Classifier Agent
version: "1.0.0"
prompt_ref: classifier-system-v1

model:
  provider: litellm
  model_id: ${ACTIVE_MODEL:-claude-sonnet-4-6}
  temperature: 0.0
  max_tokens: 2048
  base_url: https://your-litellm-proxy.example.com
  api_key_env: LITELLM_API_KEY

output_schema: ClassificationResult

gateway:
  auth_type: aws_iam

runtime:
  type: agentcore
  max_iterations: 3   # Structured output agents typically need fewer iterations
  idle_timeout_minutes: 10
  network_mode: PRIVATE
  protocol: HTTP

execution_modes:
  simulation: true
  staging: true
  production: true
```

With the corresponding Pydantic model registered in `schema_registry`:

```python
from pydantic import BaseModel

class ClassificationResult(BaseModel):
    category: str
    subcategory: str | None
    confidence: float
    reasoning: str
```

## Provider notes

### Bedrock

The Strands forced-tool path was originally designed around Bedrock's Converse API and is fully reliable. No additional configuration is needed.

### Anthropic

Works via the native forced-tool path. Temperature is not forwarded to the `AnthropicModel` constructor (it is a schema-required field but not passed through for this provider). For structured output with Anthropic, `temperature` in the blueprint has no effect on the enforced output call.

### LiteLLM

Works via the native forced-tool path for any OpenAI-compatible endpoint. Ensure your proxy supports tool-call / function-calling mode (`tool_choice="required"`) — most production-grade proxies (LiteLLM server, vLLM with OpenAI adapter, Ollama ≥ 0.3) do.

### Vertex (Gemini)

Works via the native forced-tool path. `max_tokens` and `temperature` are not forwarded to `GeminiModel`, so schema enforcement is not affected by those blueprint fields.

## The `StructuredOutputEnforcer` — historical context

Before `strands-agents 1.41.0`, the upstream forced-tool path had reliability issues for non-Bedrock providers: when the model returned `stop_reason: end_turn` without invoking the forced tool, Strands raised `StructuredOutputException` on the second retry attempt instead of recovering.

The `StructuredOutputEnforcer` hook (backed by the `instructor` library) was introduced as a workaround: it skipped the Strands forced-tool path entirely, ran the agent normally, and post-processed the final message through `instructor` with automatic retry-on-validation-error.

With the forced-tool/`finish_reason` incompatibilities resolved in `strands-agents 1.41.0`, the enforcer was removed from the loader wiring. The file `core/src/agent_core/hooks/structured_output_enforcer.py` remains in the repository as a historical reference but is dead code — it is never registered by the loader and has no effect on running agents.

{: .note }
> If you see references to `StructuredOutputEnforcer` in older documentation, blog posts, or community discussions about this platform, those references describe behavior that no longer applies. The current behavior is: `output_schema` → Strands native `structured_output_model` → works on all four providers with `strands-agents>=1.41.0`.

## Troubleshooting

**`BlueprintLoadError: schema_registry does not contain 'MySchema'`**
The `output_schema` value in the blueprint does not match any key in the `schema_registry` dict passed to `BlueprintLoader`. Check the casing and spelling of both.

**`StructuredOutputException: The model failed to invoke the structured output tool`**
The model did not conform to the schema after the configured number of retries. Consider: lowering `temperature` (closer to 0.0 tends to improve schema conformance), simplifying the Pydantic schema, or adding explicit JSON formatting instructions to the system prompt.

**Strands version too old**
If you see the enforcer-related error paths or repeated `StructuredOutputException` on non-Bedrock providers, check `pip show strands-agents`. Upgrade to `>=1.41.0`.

---

Related: [LiteLLM](litellm) — proxy configuration for OpenAI-compatible endpoints. [Agent Blueprint — `output_schema` field](../blueprints/agent-blueprint#output_schema).
