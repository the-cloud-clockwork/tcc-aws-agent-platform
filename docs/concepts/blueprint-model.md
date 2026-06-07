---
title: Blueprint Model
parent: Concepts
nav_order: 4
---

# Blueprint Model

A blueprint is the central abstraction of the AWS Agent Platform. It is a YAML file that declares everything an agent needs — model, inference provider, tools, memory, identity, policy, observability, evaluation — and the platform wires all of it into a fully running AWS agent automatically.

The developer declares *what*. The platform handles *how*.

---

## The One-Sentence Version

> A blueprint is a YAML declaration that `BlueprintLoader` reads to produce a fully wired Strands `Agent` wrapped in an `AgentCoreApp` runtime container — no boilerplate required.

---

## A Minimal Blueprint

The only required fields are `id`, `version`, `name`, `prompt_ref`, and a `model` block (which itself requires `model_id`, `temperature`, and `max_tokens`):

```yaml
id: analysis-agent
version: "1.0.0"
name: Analysis Agent
prompt_ref: analysis-agent-system-v1

model:
  provider: bedrock            # bedrock | anthropic | litellm | vertex
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  temperature: 0.1
  max_tokens: 4096
```

That is a complete, loadable agent blueprint. Everything else — tools, memory, identity, policy, observability — has safe defaults and is added only when needed.

---

## What Each Block Wires

Every top-level key in the blueprint maps to a specific AWS service or SDK component that `BlueprintLoader` assembles at load time:

| Blueprint Block | What It Configures | AWS / SDK Component |
|---|---|---|
| `model` | Inference provider and model | `BedrockModel`, `AnthropicModel`, `LiteLLMModel`, or `GeminiModel` (Strands SDK) |
| `prompt_ref` | System prompt source | Prompt Registry (S3 + DynamoDB, mode-gated) |
| `tools` | MCP tools, built-in tools, A2A agent tools | AgentCore Gateway targets, Code Interpreter, Browser, A2A clients |
| `gateway` | Inbound auth for the agent endpoint | AgentCore Gateway (JWT or IAM validation) |
| `identity` | Inbound JWT validation + outbound credential resolution | AgentCore Identity, Secrets Manager / SSM |
| `memory` | Conversation history and long-term knowledge | AgentCore Memory (short-term events + pgvector long-term) |
| `observability` | Tracing, Langfuse, audit log, cost tracking, data protection | OTEL/CloudWatch, Langfuse, DynamoDB audit, Presidio or Bedrock Guardrails |
| `evaluation` | LLM-as-judge scoring of agent behaviour | AgentCore Evaluation or Langfuse Evaluation |
| `policy` | Tool-level access control | Cedar policy engine on AgentCore Gateway |
| `runtime` | Container hosting parameters | AgentCore Runtime (microVM pool, network mode, protocol) |
| `multi_agent` | Coordinator/specialist topology | A2A server (specialist) or A2A client nodes (coordinator) |
| `execution_modes` | Which environments the agent is active in | `EXECUTION_MODE` gating throughout prompt resolution, Gateway routing, and data access |
| `output_schema` | Structured output enforcement | Strands native `structured_output_model` (requires `schema_registry` in `BlueprintLoader`) |
| `thinking` | Extended reasoning budget | Strands thinking mode (`enabled`, `budget_tokens`) |
| `artifacts` | Artifact storage tier and type hint | Artifact Store (S3 + DynamoDB, claim-check pattern) |

---

## Three Blueprint Types

The platform defines three blueprint types for the three different roles in an agent system:

| Type | File Location | Produces |
|---|---|---|
| **Agent** (`AgentBlueprint`) | `blueprints/agents/*.yaml` | AgentCore Runtime container + wired Strands agent |
| **Strategy** (`StrategyBlueprint`) | `blueprints/strategies/*.yaml` | Evaluated by a strategy-evaluation agent |
| **Workflow** (`WorkflowBlueprint`) | `blueprints/workflows/*.yaml` | AWS Step Functions state machine |

Most work involves agent blueprints. Strategy and workflow blueprints are covered in detail in the [Blueprints](../blueprints/) section.

---

## How BlueprintLoader Assembles a Blueprint

`BlueprintLoader` is the engine that turns YAML into a running agent. The assembly sequence is deterministic:

```
blueprints/agents/my-agent.yaml
        |
        v
BlueprintLoader.build_agent_session(agent_id)
        |
        +-- 1. Locate and parse YAML → AgentBlueprint (Pydantic validation)
        +-- 2. Resolve model → BedrockModel / AnthropicModel / LiteLLMModel / GeminiModel
        +-- 3. Resolve prompt → PromptRegistryClient.get(prompt_ref, mode)
        +-- 4. Wire tools → MCPClient (Gateway), BuiltinToolWiring, A2aToolConfig
        +-- 5. Wire memory → MemoryWiring → MemoryHookProvider (if strategies declared)
        +-- 6. Wire identity → credential provider decorators (if credentials declared)
        +-- 7. Wire observability → CompositeObservabilityHook (if enabled)
        +-- 8. Wire evaluation → EvaluationClient + evaluator config (if evaluators declared)
        +-- 9. Wire policy → CedarPolicyBuilder → PolicyWiring (if policy declared)
        +-- 10. Wire structured output → structured_output_model (if output_schema declared)
        +-- 11. Wire A2A server → A2AServerWrapper.from_blueprint() (if role: specialist)
        |
        v
AgentSession { agent, hooks, context }
        |
        v
AgentCoreApp(@app.entrypoint) → Docker → ECR → AgentCore Runtime → microVM
```

Steps 3 through 11 only run for the blocks that are declared. An agent with no `memory:` strategies skips step 5 entirely — no memory client is created, no hook is registered, no AGENTCORE_MEMORY_ID is required.

---

## env-template Expansion

Any string field in a blueprint supports `${VAR}` and `${VAR:-default}` env-template expansion at load time. This is most commonly used for `model.model_id` to allow runtime model switching without image rebuilds:

```yaml
model:
  provider: litellm
  model_id: ${AGENT_MODEL_ID:-claude-sonnet-4-6}
  base_url: ${LITELLM_BASE_URL}
  api_key_env: LITELLM_API_KEY
  temperature: 0.1
  max_tokens: 4096
```

At load time, `BlueprintLoader` expands `${AGENT_MODEL_ID:-claude-sonnet-4-6}` using the environment — the model running in production can differ from staging without any blueprint change.

---

## Execution Mode Isolation

`execution_modes` is a blueprint-level gate that controls which environments the agent is active in:

```yaml
execution_modes:
  simulation: true   # active in simulation (default: true)
  staging: true      # active in staging (default: false)
  production: false  # not yet promoted to production
```

`EXECUTION_MODE` is set at deployment time via the Terraform agents module. When the runtime mode is not listed as `true` in the blueprint, the agent rejects invocations with a clear error. This prevents accidentally routing production traffic to an agent that has not been through staging.

Execution mode also controls:
- Which prompt version the Prompt Registry resolves (`draft` prompts are only accessible in `simulation` and `dev` modes; only `stable` prompts are resolved in `staging` and `production`)
- Which Gateway backend targets receive tool calls (domain repos can declare mode-specific target URLs)
- Which Memory namespaces are read and written

---

## Switching Inference Provider

The `model.provider` field is the only change needed to switch inference backends:

```yaml
# Bedrock (default)
model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  temperature: 0.1
  max_tokens: 4096

# Anthropic direct API
model:
  provider: anthropic
  model_id: claude-sonnet-4-5
  api_key_env: ANTHROPIC_API_KEY
  temperature: 0.1
  max_tokens: 4096

# LiteLLM proxy (any OpenAI-compatible endpoint)
model:
  provider: litellm
  model_id: claude-sonnet-4-6
  base_url: ${LITELLM_BASE_URL}
  api_key_env: LITELLM_API_KEY
  extra_headers_env:
    CF-Access-Client-Id: CF_CLIENT_ID
    CF-Access-Client-Secret: CF_CLIENT_SECRET
  temperature: 0.1
  max_tokens: 4096

# Vertex AI (Google)
model:
  provider: vertex
  model_id: gemini-2.0-flash
  temperature: 0.1
  max_tokens: 4096
```

All other blueprint blocks — memory, tools, policy, observability — remain unchanged. The provider swap is confined to the `model:` block. See [Inference Providers](../inference/) for provider-specific setup and caveats.

---

## Blueprint vs. Code

The table below shows what lives in the blueprint versus what domain developers write in code:

| Concern | Blueprint (YAML) | Code |
|---|---|---|
| Which model and provider | `model.provider`, `model.model_id` | — |
| Which tools the agent can call | `tools[].mcp`, `tools[].builtin`, `tools[].a2a` | Tool implementations (Lambda / MCP server) |
| What the system prompt says | `prompt_ref` → Prompt Registry | `build_prompt()` function in `AgentConfigRegistry` |
| Memory strategy configuration | `memory.strategies` | — |
| Who can call the agent (inbound auth) | `identity.authorizer` | — |
| What credentials the agent uses (outbound) | `identity.credentials` | — |
| Which tool calls are permitted | `policy.rules` | — |
| Observability and evaluation settings | `observability`, `evaluation` | — |
| Runtime sizing and network mode | `runtime` | — |
| The agent entrypoint | — (generated) | `app.py` — 5-line handler, identical for every agent |

The developer writes: the prompt builder (one function per agent), tool implementations (Lambda / MCP), and the five-line `app.py`. Every other concern is configuration.

---

## Where Blueprints Live

```
blueprints/
  agents/
    my-agent.yaml          # AgentBlueprint — declares the full agent
  strategies/
    my-strategy.yaml       # StrategyBlueprint — trigger conditions and parameters
  workflows/
    daily-pipeline.yaml    # WorkflowBlueprint — Step Functions DAG
```

`BlueprintLoader` discovers blueprints by scanning the `blueprints/` directory. File discovery tries `{id}.yaml` first, then `{id}.yml`, then falls back to scanning all YAML files for a matching `id` field.

Blueprint IDs use kebab-case by convention (e.g. `analysis-agent`, `data-processor`), matching the filenames in the shipped examples.

---

## Next Steps

- [Platform vs. Domain](platform-vs-domain) — the full responsibility boundary between platform and domain repo
- [How It Works](how-it-works) — end-to-end assembly and request flow with sequence diagrams
- [Agent Blueprint Reference](../blueprints/agent-blueprint) — every field documented with types and defaults
- [Inference Providers](../inference/) — provider-specific setup for bedrock, anthropic, litellm, and vertex
