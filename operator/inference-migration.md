# Inference Provider Migration — Decoupling Strategy

> **Created:** 2026-04-08
> **Owner:** Nestor Colt
> **Status:** Investigation complete. Ready for staged implementation.
> **Source of truth** for provider-agnostic inference migration.

---

## Current State: Bedrock Coupling Audit

The platform is **deeply coupled to AWS Bedrock** across 10 integration points spanning SDK, infrastructure, and observability layers.

### Coupling Map

| # | Layer | Coupling Point | File(s) | Severity |
|---|-------|---------------|---------|----------|
| 1 | **Model instantiation** | `BedrockModel` is the only implemented provider path in `_build_model_config()` | `loader.py:280-302` | **Critical** |
| 2 | **Schema** | `ModelConfig.provider: Literal["bedrock", "anthropic", "litellm", "vertex"]` — only `bedrock` has a code path | `model_config.py:9-27` | Medium |
| 3 | **Blueprints** | All 12 YAML blueprints use `provider: bedrock` with Bedrock model ID format (`us.anthropic.claude-*`) | `data/blueprints/agents/*.yaml` | Medium |
| 4 | **Runtime env** | `BEDROCK_REGION` is a **hard requirement** — `_build_model_config()` raises if missing | `loader.py:289-293` | **Critical** |
| 5 | **Guardrail hook** | `boto3.client("bedrock-runtime").apply_guardrail()` — Bedrock API call | `guardrail_hook.py`, `data_protection.py:175` | Medium |
| 6 | **Cost tracker** | Env vars `BEDROCK_MODEL_PRICING`, `BEDROCK_DEFAULT_PRICING` — Bedrock pricing format | `cost_tracker.py` | Low |
| 7 | **Evaluation** | `bedrockEvaluatorModelConfig` hardcoded in evaluation API payload | `evaluation/client.py:148-155` | Medium |
| 8 | **IAM** | `bedrock:InvokeModel`, trust principal `bedrock-agentcore.amazonaws.com` | `modules/agents/iam.tf` | Infra-only |
| 9 | **Runtime infra** | `aws_bedrockagentcore_agent_runtime` — agents deploy as AgentCore microVMs | `modules/agents/runtime.tf` | Infra-only |
| 10 | **Package dep** | `bedrock-agentcore>=0.1.0` in `pyproject.toml` | `core/pyproject.toml:20` | Infra-only |

### What's Already Right

- `ModelConfig` schema **already declares** `Literal["bedrock", "anthropic", "litellm", "vertex"]` — the schema is provider-aware, the implementation isn't.
- Strands SDK **natively supports** 12 model providers: `BedrockModel`, `OpenAIModel`, `AnthropicModel`, `LiteLLMModel`, `GeminiModel`, `OllamaModel`, `MistralModel`, `LlamaAPIModel`, `LlamaCppModel`, `SageMakerAIModel`, `WriterModel`, `OpenAIResponsesModel`.
- All providers implement the same `Model` ABC: `update_config()`, `get_config()`, `structured_output()`, `stream()`.
- The `Agent()` constructor accepts any `Model` subclass via `model=` kwarg — **zero Bedrock assumption** at the agent level.

---

## Official AWS Patterns (from amazon-bedrock-agentcore-samples)

### Pattern 1: BedrockModel (default, most samples)
```python
from strands.models import BedrockModel
model = BedrockModel(model_id=os.getenv("MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"))
agent = Agent(model=model)
```

### Pattern 2: OpenAIModel + AgentCore Identity (credential injection)
```python
from strands.models.openai import OpenAIModel
from bedrock_agentcore.identity.auth import requires_api_key

@requires_api_key(provider_name="openai-apikey-provider")
async def need_api_key(*, api_key: str):
    os.environ["OPENAI_API_KEY"] = api_key

model = OpenAIModel(client_args={"api_key": os.environ["OPENAI_API_KEY"]}, model_id="gpt-4o")
```

### Pattern 3: LiteLLMModel (proxy to any backend)
```python
from strands.models.litellm import LiteLLMModel
model = LiteLLMModel(model_id="bedrock/converse/us.anthropic.claude-3-7-sonnet-20250219-v1:0")
# or: model_id="openai/gpt-4o"
# or: model_id="anthropic/claude-3-5-sonnet"
# or: model_id="ollama/llama3"
```

### Pattern 4: OpenAI-compatible endpoint (custom base_url)
```python
from strands.models.openai import OpenAIModel
model = OpenAIModel(
    client_args={"api_key": "sk-...", "base_url": "https://my-proxy.example.com/v1"},
    model_id="my-model"
)
```

### Key Insight
AgentCore Runtime is **framework-agnostic** — `model_id` is NOT in `.bedrock_agentcore.yaml`. Model selection is purely code-level. Infrastructure (microVM, gateway, memory) is orthogonal to inference provider.

---

## Decoupling Strategy — 3 Stages

### Stage 1: SDK Model Factory (Effort: Small — 1 session)

**Goal:** Make `_build_model_config()` dispatch to all 4 declared providers. Zero infra changes. Bedrock remains default.

**Changes:**

1. **`core/src/agent_core/blueprints/loader.py`** — Replace the single `BedrockModel` path with a factory dispatch:

```python
@staticmethod
def _build_model_config(model: ModelConfig, thinking: Any = None) -> dict[str, Any]:
    match model.provider:
        case "bedrock":
            from strands.models import BedrockModel
            bedrock_region = os.environ.get("BEDROCK_REGION", "")
            if not bedrock_region:
                raise ConfigurationError("BEDROCK_REGION env var required for bedrock provider")
            provider_model = BedrockModel(
                model_id=model.model_id,
                region_name=bedrock_region,
                max_tokens=model.max_tokens,
            )

        case "anthropic":
            from strands.models.anthropic import AnthropicModel
            provider_model = AnthropicModel(
                model_id=model.model_id,
                max_tokens=model.max_tokens,
            )

        case "litellm":
            from strands.models.litellm import LiteLLMModel
            litellm_kwargs = {}
            base_url = os.environ.get("LITELLM_BASE_URL")
            api_key = os.environ.get("LITELLM_API_KEY")
            if base_url:
                litellm_kwargs["client_args"] = {"base_url": base_url}
            if api_key:
                litellm_kwargs["client_args"] = {**litellm_kwargs.get("client_args", {}), "api_key": api_key}
            provider_model = LiteLLMModel(
                model_id=model.model_id,
                **litellm_kwargs,
            )

        case "vertex":
            from strands.models.gemini import GeminiModel
            provider_model = GeminiModel(model_id=model.model_id)

        case _:
            raise ConfigurationError(f"Unsupported model provider: {model.provider}")

    kwargs = {"model": provider_model}
    if thinking:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking.budget_tokens}
    return kwargs
```

2. **`core/src/agent_core/schemas/model_config.py`** — Add optional fields for non-Bedrock providers:

```python
class ModelConfig(BaseModel):
    provider: Literal["bedrock", "anthropic", "litellm", "vertex"] = "bedrock"
    model_id: str = Field(...)
    temperature: float = Field(..., ge=0.0, le=1.0)
    max_tokens: int = Field(..., gt=0)
    cache_prompt: str | None = Field(default="default")
    cache_tools: str | None = Field(default="default")
    # Stage 1: provider-specific optional fields
    base_url: str | None = Field(default=None, description="API base URL for litellm/openai-compatible providers")
    api_key_env: str | None = Field(default=None, description="Env var name containing the API key (never the key itself)")
```

3. **`modules/agents/runtime.tf`** — Add optional env var passthrough for non-Bedrock providers:

```hcl
# In the environment block (conditional merge):
var.litellm_base_url != "" ? { LITELLM_BASE_URL = var.litellm_base_url } : {},
var.litellm_api_key_secret != "" ? { LITELLM_API_KEY = data.aws_ssm_parameter.litellm_key[0].value } : {},
```

4. **No blueprint changes needed** — existing blueprints keep `provider: bedrock`. New blueprints can use any provider.

**Validation:** All existing blueprints continue to work unchanged. New blueprint with `provider: litellm` routes to LiteLLMModel.

---

### Stage 2: Observability & Hooks Decoupling ✅ COMPLETE (2026-04-09)

**Goal:** Remove Bedrock assumptions from guardrails, cost tracking, and evaluation. Make these features work with any provider or degrade gracefully.

**Delivered:**

- [x] **Guardrail model kwargs no-op on non-Bedrock** — `build_guardrail_model_kwargs()` now returns `{}` instead of raising when `BEDROCK_GUARDRAIL_ID` is absent. Fixes latent crash in LiteLLM agents.
- [x] **Guardrail hook provider-gated** — `loader.py` only registers `GuardrailHook` when `blueprint.model.provider == "bedrock"` AND the env var is set. LiteLLM agents no longer silently call Bedrock `ApplyGuardrail`.
- [x] **Presidio PII guardrail** — New `PresidioGuardrailHook` in `core/src/agent_core/hooks/presidio_guardrail.py`. MIT-licensed, provider-agnostic. Selected via blueprint `observability.data_protection.provider: presidio`. Lazy-loads Presidio engines so import cost is zero. Dependency in `presidio` optional extra.
- [x] **Cost tracker env rename** — `BEDROCK_MODEL_PRICING` / `BEDROCK_DEFAULT_PRICING` renamed to `MODEL_PRICING` / `MODEL_DEFAULT_PRICING`. Legacy envs still honored as deprecated aliases (warning logged). Built-in defaults for `claude-sonnet-4-6` / `claude-haiku-4-6` so token→USD works out of the box on LiteLLM.
- [x] **Langfuse evaluation provider** — New `EvaluationProvider` protocol in `evaluation/provider.py`. `LangfuseEvaluationClient` in `evaluation/langfuse_client.py` uses the Langfuse SDK for scoring + custom judge registration. Selected via blueprint `evaluation.provider: langfuse`. `agentcore` stays default.
- [x] **Observability toggle wired** — `loader.py` now honors `blueprint.observability.enabled`. Setting it to `false` disables Langfuse / audit log / structured log / cost tracking hooks entirely.
- [x] **Dead YAML cleanup** — Removed `observability.dashboard.*` and `observability.audit_log.ttl_days` blocks from all 9 QITP blueprints (schema retained with defaults for future Bedrock agents).
- [x] **Tests** — `TestPhase2Decoupling` in `test_block9_strands_integration.py` covers: guardrail no-op, env alias, Presidio hook, EvaluationProvider protocol compliance, Langfuse client creds validation, wiring dispatch in both directions.

**Key insight confirmed:** Langfuse is already integrated at two layers (LiteLLM proxy + agent `LangfuseHook`), so traces on non-Bedrock agents have been working the entire time. Stage 2 was about closing the guardrail/eval gaps and making provider selection explicit in the blueprint schema.

---

### Stage 3: Infrastructure Optionality (Effort: Large — 3-5 sessions)

**Goal:** Support running agents outside AgentCore Runtime (e.g., ECS, Lambda, local) while keeping AgentCore as the primary deployment target.

**Changes:**

1. **Runtime abstraction** — `AgentCoreApp` wraps `BedrockAgentCoreApp`. Create a `RuntimeServer` protocol:
   - `AgentCoreServer` (current): BedrockAgentCoreApp on port 8080
   - `StandaloneServer` (new): plain Starlette/FastAPI on configurable port
   - Selection via `RuntimeConfig.runtime_type: Literal["agentcore", "standalone"]`

2. **Memory abstraction** — `MemoryClient` imports from `bedrock_agentcore.memory`:
   - Create `MemoryProvider` protocol
   - `AgentCoreMemory`: current implementation
   - `DynamoDBMemory`: direct DynamoDB (no AgentCore dependency)
   - `InMemoryProvider`: for local dev/testing

3. **Gateway abstraction** — `GatewayClient` depends on AgentCore Gateway:
   - Keep as optional: if `AGENTCORE_GATEWAY_URL` is set, use it
   - If not set, tools resolve directly (already have `GATEWAY_DIRECT_MCP=true` pattern from KI-001)

4. **Terraform modules** — Add alternative deployment module:
   - `modules/agents` stays as AgentCore deployment
   - `modules/agents_ecs` (new, future) for ECS Fargate deployment
   - Same blueprint YAML input, different infrastructure output

5. **Package dependencies** — Make `bedrock-agentcore` optional:
   ```toml
   # pyproject.toml
   dependencies = ["strands-agents[otel]>=1.0.0,<2", ...]
   [project.optional-dependencies]
   agentcore = ["bedrock-agentcore>=0.1.0"]
   standalone = []  # no extra deps
   ```

**This stage is the most invasive** and should only be pursued if there's a concrete need to run agents outside AgentCore (e.g., cost optimization, multi-cloud, local dev).

---

## Decision Matrix

| Stage | What You Get | What You Keep | Effort | Risk |
|-------|-------------|---------------|--------|------|
| **1** | Any Strands model provider via blueprint YAML | All infra unchanged, Bedrock default | Small (1 session) | **Low** — additive, no breaking changes |
| **2** | Guardrails/eval work with non-Bedrock providers | AgentCore platform features | Medium (1-2 sessions) | **Low** — graceful degradation only |
| **3** | Run agents outside AgentCore entirely | AgentCore as primary target | Large (3-5 sessions) | **Medium** — requires careful abstraction |

---

## Recommended Approach

**Stage 1 is the high-value, low-risk move.** It unlocks:
- LiteLLM proxy → any of 100+ model providers (OpenAI, Anthropic direct, Azure, Mistral, local Ollama)
- Direct Anthropic API → no Bedrock markup pricing
- Vertex/Gemini → Google models
- All through a 1-file change in `loader.py` + 2 optional fields in `ModelConfig`

**Stage 2** when you have a non-Bedrock agent in production and need guardrails/eval on it.

**Stage 3** only if AgentCore Runtime becomes a constraint (cost, region availability, vendor lock-in strategy).

---

## Implementation Checklist — Stage 1 ✅ COMPLETE (2026-04-09)

- [x] Update `_build_model_config()` in `loader.py` with match/case dispatch
- [x] Add `base_url`, `api_key_env`, `extra_headers_env` to `ModelConfig`
- [x] Add `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `CF_ACCESS_*` env var passthrough in `modules/agents/runtime.tf`
- [x] Add `litellm`, `anthropic`, `structured_output` optional extras in `pyproject.toml`
- [x] Swap gap-detector blueprint to `provider: litellm` (first real validation)
- [x] Build `StructuredOutputEnforcer` hook (instructor-based) for non-Bedrock `output_schema` support
- [x] Deploy all 9 QITP agents on LiteLLM proxy + Cloudflare Access service tokens
- [x] E2E validation: weekly-gap-analysis pipeline SUCCEEDED in 31s, 16/16 states (exec `a2ad23f0-f8fd-4ef2-bbcf-fd2c4f8c1c51`)
- [x] Update CLAUDE.md with provider configuration docs

---

## Environment Variables by Provider

| Provider | Required Env Vars | Optional |
|----------|------------------|----------|
| `bedrock` | `BEDROCK_REGION` | — |
| `anthropic` | `ANTHROPIC_API_KEY` (via api_key_env) | — |
| `litellm` | `LITELLM_API_KEY` (via api_key_env) | `LITELLM_BASE_URL` |
| `vertex` | `GOOGLE_APPLICATION_CREDENTIALS` | `VERTEX_PROJECT`, `VERTEX_LOCATION` |

---

## LiteLLM Integration — Special Note

The operator runs a LiteLLM proxy at `llm.homeofanton.com`. This is the **fastest path to provider-agnostic inference**:

1. Set `provider: litellm` in a blueprint
2. Set `LITELLM_BASE_URL=https://llm.homeofanton.com` as env var
3. Set `model_id` to any LiteLLM-supported format (e.g., `anthropic/claude-sonnet-4-20250514-v1:0`)
4. LiteLLM handles routing, key management, fallbacks, cost tracking

This means Stage 1 gives you immediate access to every model your LiteLLM proxy already supports — without any Bedrock dependency for inference.

---

## Constraints & Guardrails

1. **AgentCore Runtime stays** — it provides microVM isolation, Gateway, Memory, Identity, Evaluation. These are platform features, not inference features. Even with `provider: litellm`, agents still deploy on AgentCore.

2. **Bedrock remains default** — `ModelConfig.provider` defaults to `"bedrock"`. No existing blueprint changes. Zero breakage.

3. **Secrets via env vars only** — API keys for non-Bedrock providers are referenced by env var name (`api_key_env: "ANTHROPIC_API_KEY"`), never stored in blueprint YAML.

4. **IAM changes minimal** — `bedrock:InvokeModel` stays for Bedrock blueprints. Non-Bedrock providers don't need Bedrock IAM — they use API keys via SSM/Secrets Manager.

5. **No backward compatibility concerns** — Stage 1 is purely additive. The existing `provider: bedrock` path is untouched.
