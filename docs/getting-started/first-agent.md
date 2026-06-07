---
title: First Agent
nav_order: 3
parent: Getting Started
---

# First Agent

A complete step-by-step tutorial from an empty directory to a running agent on AgentCore Runtime.

You write: one YAML blueprint, one prompt builder, and one 5-line handler. The platform generates everything else.

---

## What You Are Building

A general-purpose assistant agent that:

- Runs in an isolated microVM per session on AgentCore Runtime
- Routes tool calls through AgentCore Gateway to your domain MCP server
- Persists conversation history with short-term and long-term Memory
- Validates inbound requests with Cognito JWT
- Streams OTEL traces to CloudWatch automatically

---

## Step 1: Write the Blueprint

The blueprint is the single source of truth for your agent. Every runtime behavior — model selection, tool routing, memory persistence, auth, observability — is declared here.

Create `blueprints/agents/assistant.yaml`:

```yaml
id: assistant
name: General Purpose Assistant
version: "1.0.0"
description: "General-purpose assistant with tool access and memory"

# Required: references a versioned prompt in the Prompt Registry.
# The loader resolves this at startup — direct Lambda invoke first,
# then HTTP fallback, then local file (useful in dev).
prompt_ref: assistant-system-v1

# Runtime: hosts this agent in an isolated microVM per session.
# network_mode: PRIVATE means the container runs inside your VPC.
runtime:
  type: agentcore
  max_iterations: 15
  idle_timeout_minutes: 15
  network_mode: PRIVATE
  protocol: HTTP

# Model: provider-agnostic. Switch provider by changing these two fields.
# model_id, temperature, and max_tokens are required — no platform defaults.
# provider defaults to "bedrock". Use ${VAR:-fallback} for env-template expansion.
model:
  provider: bedrock
  model_id: ${MODEL_ID}
  temperature: 0.3
  max_tokens: 4096

# Tools: MCP targets routed through Gateway.
# The platform wires the MCPClient; domain provides the Lambda or container.
tools:
  - mcp: assistant-tools-mcp
    tools: [search_knowledge_base, create_note, list_notes]

# Gateway inbound auth.
gateway:
  auth_type: aws_iam

# Memory: two tiers wired automatically when strategies are declared.
# Short-term: last short_term_k turns injected into system prompt each session.
# Long-term: facts extracted asynchronously, retrieved by semantic similarity.
# There is no `mode` field — strategies activate memory automatically.
# SUMMARIZATION is accepted as an alias for SUMMARY.
memory:
  strategies:
    - type: USER_PREFERENCE
      name: PreferenceLearner
      namespace: "user/{actorId}/preferences/"
    - type: SEMANTIC
      name: FactExtractor
      namespace: "user/{actorId}/facts/"
    - type: SUMMARY
      name: Summarizer
      namespace: "user/{actorId}/{sessionId}/summaries/"
  event_expiry_days: 30
  short_term_k: 5

# Identity: Cognito JWT validates every inbound request before your code runs.
# Outbound credential types are api_key and oauth2 only.
identity:
  authorizer:
    type: cognito_jwt
    user_pool_id: ${COGNITO_POOL_ID}
    client_id: ${COGNITO_CLIENT_ID}
  credentials:
    - name: notes-api-key
      type: api_key
      provider: notes-apikey-provider

# Observability: all application-level hooks (Langfuse, audit, cost tracking)
# are gated by enabled: true. OTEL auto-instrumentation is separate — it is
# controlled by the Dockerfile generated at deploy time.
# audit_log writes to DynamoDB (not CloudWatch).
observability:
  enabled: true
  trace_attributes:
    environment: development
    agent.version: "1.0.0"
  audit_log:
    enabled: true
    ttl_days: 1825      # 5 years

# Evaluation: online evaluation scores a percentage of live sessions.
# provider defaults to "agentcore"; set to "langfuse" for provider-agnostic eval.
evaluation:
  provider: agentcore   # agentcore | langfuse
  online:
    sampling_rate: 10
    evaluators:
      - Builtin.GoalSuccessRate
      - Builtin.Correctness
      - Builtin.ToolSelectionAccuracy

# Policy: Cedar access control attached to the Gateway.
# mode: LOG_ONLY during development; switch to ENFORCE in production.
policy:
  engine: AssistantPolicies
  mode: LOG_ONLY
  rules:
    - name: notes_write_limit
      allow: create_note
      when: "context.input.content.length <= 10000"
```

### What Each Block Does

| YAML Key | What the Platform Wires Automatically |
|----------|--------------------------------------|
| `runtime:` | `@app.entrypoint` decorator, Dockerfile with OTEL layer, ECR push, Runtime registration |
| `model:` | Strands `BedrockModel` / `LiteLLMModel` / `AnthropicModel` / `GeminiModel` — dispatched by `provider` |
| `tools:` + `gateway:` | `MCPClient` connected to `${GATEWAY_URL}`, MCP target registrations |
| `memory:` | `MemoryHookProvider` — loads history on agent init, saves turns on each message |
| `identity:` | Runtime JWT validation, credential provider registrations |
| `observability:` | `CompositeObservabilityHook` (Langfuse, audit log, structured logger, cost tracker) |
| `evaluation:` | Online evaluation config against the agent's OTEL traces |
| `policy:` | Cedar policies translated and attached to the Gateway |

---

## Step 2: Write the System Prompt

Create `prompts/assistant-system-v1.txt`:

```
You are a helpful assistant with access to a knowledge base and note-taking tools.

Use search_knowledge_base to look up information before answering factual questions.
Use create_note and list_notes to help users manage their notes.

Be concise and accurate. When you are unsure, say so.
```

Push this to the Prompt Registry before deploying:

```bash
agentcli prompt push \
  --id assistant-system-v1 \
  --file prompts/assistant-system-v1.txt \
  --env dev
```

---

## Step 3: Write the Prompt Builder

The prompt builder is the only domain-specific code you write per agent. It constructs the per-invocation prompt from your input parameters.

Create `src/myapp/agent_configs.py`:

```python
from agent_core import AgentConfig, AgentConfigRegistry

REGISTRY = AgentConfigRegistry()

REGISTRY.register(AgentConfig(
    agent_id="assistant",
    operation_name="assist",
    required_fields=["user_request"],
    build_prompt=lambda params, idem_key: (
        f"[Task ID: {idem_key}]\n\n"
        f"User request: {params['user_request']}\n\n"
        "Respond helpfully and concisely. Use tools when needed."
    ),
))
```

`AgentConfigRegistry` is the complete interface between your domain logic and the platform. Everything else — wiring the prompt to the agent, injecting memory context, attaching tools — is handled by `BlueprintLoader`.

---

## Step 4: Write the Handler

Every agent uses an identical 5-line handler. The blueprint, not the handler, determines all runtime behavior.

Create `src/myapp/app.py`:

```python
from agent_core import AgentCoreApp, BlueprintLoader, GenericHandler
from myapp.agent_configs import REGISTRY

HANDLER = GenericHandler(
    loader=BlueprintLoader(blueprints_dir="blueprints", config_registry=REGISTRY)
)
app = AgentCoreApp(handler=HANDLER)
```

`BlueprintLoader` reads `blueprints/agents/assistant.yaml`, resolves all declared blocks, and builds a Strands `Agent` with the correct model, Gateway tools, memory hooks, identity decorators, and OTEL attributes. `AgentCoreApp` exposes `POST /invocations` and `GET /ping` on port 8080.

For specialist agents in a multi-agent graph, `BlueprintLoader.build_entrypoint()` auto-mounts an A2A sidecar server when `multi_agent.role: specialist` is declared in the blueprint — no additional code needed.

---

## Step 5: Validate the Blueprint

```bash
agentcli blueprint lint blueprints/agents/assistant.yaml
```

Expected output:

```
Validating blueprints/agents/assistant.yaml ... OK
  runtime: agentcore, PRIVATE, HTTP
  model: ${MODEL_ID} via bedrock
  tools: 1 MCP target(s), 3 tool(s)
  memory: 3 strategies, 5 short-term turns
  identity: cognito_jwt, 1 credential provider(s)
  observability: enabled, audit_log: enabled
  evaluation: online @ 10%, 3 evaluator(s)
  policy: LOG_ONLY, 1 rule(s)

All blueprints valid.
```

If validation fails, the CLI reports the field path and the expected format. Fix each reported issue before proceeding.

---

## Step 6: Deploy

With infrastructure in place (see [Infrastructure]({{ '/docs/infrastructure/' | relative_url }})):

```bash
# Deploy to dev environment
agentcli deploy agent blueprints/agents/assistant.yaml --env dev
```

Under the hood, `agentcli deploy agent`:

1. Reads the blueprint and generates a `Dockerfile` with the OTEL instrumentation layer
2. Builds the Docker image
3. Authenticates to ECR and pushes the image
4. Calls the AgentCore API to register or update the Runtime
5. Reports the Runtime ARN and endpoint URL

---

## Step 7: Invoke Your Agent

Once deployed, invoke via the AgentCore Runtime API:

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "${RUNTIME_ARN}" \
  --payload '{"operation": "assist", "user_request": "What notes do I have for today?"}' \
  --session-id "$(uuidgen)"
```

---

## What You Did NOT Write

The platform generated all of this from the blueprint:

- The `@app.entrypoint` decorator and AgentCore wiring
- The `BedrockModel` (or `LiteLLMModel` / `AnthropicModel` / `GeminiModel`) instantiation
- The `MCPClient` connecting to Gateway at `${GATEWAY_URL}`
- The `MemoryHookProvider` that loads history on agent init and saves turns on each message
- The `@requires_access_token` / `@requires_api_key` decorators for outbound credentials
- The Dockerfile with OTEL instrumentation
- The `trace_attributes` dict on the Strands `Agent`
- The evaluation online config against the agent's OTEL traces
- The Cedar policy attachment to the Gateway

---

## Switching Providers

To switch from Bedrock to LiteLLM, change two lines in the blueprint:

```yaml
model:
  provider: litellm                        # was: bedrock
  model_id: claude-sonnet-4-6             # name the proxy expects
  temperature: 0.3
  max_tokens: 4096
  base_url: ${LITELLM_BASE_URL}
  api_key_env: LITELLM_API_KEY
```

No handler or infrastructure changes required. Redeploy and the new provider is live.

---

## Next Steps

- [Agent Blueprint Spec]({{ '/docs/blueprints/agent-blueprint' | relative_url }}) — complete YAML field reference
- [Inference Providers]({{ '/docs/inference/' | relative_url }}) — Bedrock, LiteLLM, Anthropic, and Vertex in depth
- [Concepts: How It Works]({{ '/docs/concepts/how-it-works' | relative_url }}) — deep dive into the BlueprintLoader pipeline
- [Infrastructure]({{ '/docs/infrastructure/' | relative_url }}) — Terraform modules and deployment patterns
- [SDK Reference — Runtime]({{ '/docs/sdk/runtime' | relative_url }}) — `AgentCoreApp`, `GenericHandler`, `BlueprintLoader` API
