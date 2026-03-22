---
title: First Agent
nav_order: 3
parent: Getting Started
grand_parent: Documentation
---

# First Agent

A complete, step-by-step tutorial that takes you from an empty directory to a running agent on AgentCore Runtime.

You will write: one YAML blueprint, one prompt builder, and one 5-line handler. The platform generates everything else.

---

## What You Are Building

A general-purpose assistant agent that:

- Runs in an isolated microVM per session on AgentCore Runtime
- Routes tool calls through AgentCore Gateway to a domain Lambda
- Persists conversation history with Memory
- Validates inbound requests with Cognito JWT
- Streams OTEL traces to CloudWatch automatically

---

## Step 1: Write the Blueprint

The blueprint is the single source of truth for your agent. Every runtime behavior — model selection, tool routing, memory persistence, auth, observability — is declared here.

Create `blueprints/agents/assistant.yaml`:

```yaml
agent_id: assistant
version: "1.0.0"
description: "General-purpose assistant with tool access and memory"

# --- Block 1: Runtime ---
# Hosts this agent in an isolated microVM per session.
# network_mode: PRIVATE means the container runs in your VPC.
runtime:
  type: agentcore
  max_iterations: 15
  idle_timeout_minutes: 15
  network_mode: PRIVATE
  protocol: HTTP

# --- Block 9: Model (Strands/Bedrock) ---
# Model is resolved at load time from the blueprint.
# Never hardcode a model ID — use an environment variable.
model:
  provider: bedrock
  model_id: ${MODEL_ID}
  region: ${BEDROCK_REGION}

# --- Block 2: Gateway Tools ---
# The agent sees these as MCP tools.
# The platform wires them to Gateway targets; domain provides the Lambda.
tools:
  - mcp: assistant-tools-mcp
    tools: [search_knowledge_base, create_note, list_notes]

# --- Block 4: Memory ---
# Short-term: last 5 turns injected into the system prompt each session.
# Long-term: semantic facts extracted asynchronously and retrieved by similarity.
memory:
  mode: MANAGED
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

# --- Block 3: Identity ---
# Inbound: Cognito JWT validates every request before your code runs.
# Outbound: the agent can acquire credentials for external APIs.
identity:
  authorizer:
    type: cognito_jwt
    user_pool_id: ${COGNITO_POOL_ID}
    client_id: ${COGNITO_CLIENT_ID}
  credentials:
    - name: notes-api-key
      type: api_key
      provider: notes-apikey-provider

# --- Block 6: Observability ---
# OTEL auto-instrumentation is enabled by including aws-opentelemetry-distro
# in the generated Dockerfile. trace_attributes appear on every span.
observability:
  enabled: true
  trace_attributes:
    environment: production
    agent.version: "1.0.0"
  audit_log:
    enabled: true
    ttl_years: 5

# --- Block 7: Evaluation ---
# Online evaluation scores a percentage of live sessions continuously.
# Results appear in the GenAI Observability dashboard.
evaluation:
  online:
    sampling_rate: 100
    evaluators:
      - Builtin.GoalSuccessRate
      - Builtin.Correctness
      - Builtin.ToolSelectionAccuracy

# --- Block 8: Policy ---
# Cedar policies attached to the Gateway enforce access control per tool call.
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

| Block | YAML Key | What the Platform Does |
|-------|---------|------------------------|
| Runtime | `runtime:` | Generates `@app.entrypoint`, Dockerfile, ECR push, Runtime registration |
| Gateway | `tools:` | Registers MCP targets, injects `MCPClient` wired to `${GATEWAY_URL}` |
| Memory | `memory:` | Generates `MemoryHookProvider`, injects into Strands `Agent` |
| Identity | `identity:` | Configures Runtime JWT validation, registers credential providers |
| Observability | `observability:` | Adds OTEL Dockerfile layer, wraps entrypoint with `opentelemetry-instrument` |
| Evaluation | `evaluation:` | Creates online evaluation config against the agent's OTEL traces |
| Policy | `policy:` | Generates Cedar policies, attaches policy engine to Gateway |

---

## Step 2: Create the Prompt Builder

The prompt builder is the only domain-specific code you write per agent. It constructs the system prompt and per-invocation prompt from your business parameters.

Create `src/my_domain/agent_configs.py`:

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

The `AgentConfigRegistry` is the complete interface between domain logic and the platform. Everything else — wiring the prompt to the agent, injecting memory context, attaching tools — is handled by `BlueprintLoader`.

---

## Step 3: Create the Handler

Every domain agent uses an identical 5-line handler. The blueprint, not the handler, determines all runtime behaviour.

Create `src/my_domain/app.py`:

```python
from agent_core import AgentCoreApp, BlueprintLoader, GenericHandler

HANDLER = GenericHandler(
    loader=BlueprintLoader(blueprints_dir="blueprints", config_registry=REGISTRY)
)
app = AgentCoreApp(handler=HANDLER)
```

That is the complete handler. `BlueprintLoader` reads `blueprints/agents/assistant.yaml`, resolves all 12 blocks, builds a Strands `Agent` with the correct model, Gateway tools, memory hooks, identity decorators, and OTEL attributes, then hands it to `GenericHandler`. `AgentCoreApp` exposes `POST /invocations` and `GET /ping` on port 8080.

---

## Step 4: Validate the Blueprint

Before deploying, confirm the YAML is structurally valid:

```bash
agentcli blueprint lint blueprints/
```

Expected output:

```
Validating blueprints/agents/assistant.yaml ... OK
  runtime: agentcore, PRIVATE, HTTP
  model: ${MODEL_ID} via bedrock
  tools: 1 MCP target(s), 3 tool(s)
  memory: MANAGED, 3 strategies, 5 short-term turns
  identity: cognito_jwt, 1 credential provider(s)
  observability: enabled, audit_log: enabled
  evaluation: online @ 100%, 3 evaluator(s)
  policy: LOG_ONLY, 1 rule(s)

All blueprints valid.
```

If validation fails, the CLI reports the field path and the expected format. Fix each reported issue before proceeding.

---

## Step 5: Build and Deploy

With infrastructure already deployed (see [Infrastructure]({{ '/docs/infrastructure/' | relative_url }})), deploy the agent:

```bash
# Validate all blueprints
agentcli blueprint lint blueprints/

# Deploy to the target environment
agentcli deploy --env production
```

Under the hood, `agentcli deploy`:

1. Reads the blueprint and generates a production `Dockerfile` with the OTEL layer
2. Builds the Docker image locally
3. Authenticates to ECR and pushes the image
4. Calls the AgentCore API to register or update the Runtime
5. Reports the Runtime ARN and endpoint URL

---

## What You Did NOT Write

The platform generated all of this from the blueprint:

- The `@app.entrypoint` decorator and AgentCore wiring
- The `BedrockModel` instantiation with the correct model ID and region
- The `MCPClient` connecting to Gateway at `${GATEWAY_URL}`
- The `MemoryHookProvider` that loads history on agent init and saves turns on message add
- The `@requires_access_token` / `@requires_api_key` decorators for outbound credentials
- The Dockerfile with OTEL instrumentation
- The `trace_attributes` dict on the Strands `Agent`
- The evaluation online config
- The Cedar policy attachment to the Gateway

---

## Invoking Your Agent

Once deployed, invoke via the Runtime API:

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "${RUNTIME_ARN}" \
  --payload '{"operation": "assist", "user_request": "What notes do I have for today?"}' \
  --session-id "$(uuidgen)"
```

Or via the CLI:

```bash
agentcli invoke --agent assistant \
  --env production \
  --payload '{"operation": "assist", "user_request": "What notes do I have for today?"}'
```

---

## Next Steps

- [The 12 Building Blocks]({{ '/docs/architecture/building-blocks' | relative_url }}) — deep dive into every blueprint block
- [Agent Blueprint Spec]({{ '/docs/blueprints/agent-blueprint' | relative_url }}) — complete YAML field reference
- [SDK Reference — Runtime]({{ '/docs/sdk/runtime' | relative_url }}) — `AgentCoreApp`, `GenericHandler`, `BlueprintLoader` API
- [Infrastructure]({{ '/docs/infrastructure/' | relative_url }}) — Terraform modules and deployment patterns
