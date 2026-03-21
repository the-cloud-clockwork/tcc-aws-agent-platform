# Vision — AWS Agent Platform

## One-Liner

**A configuration-driven, domain-agnostic runtime that lets you declare AI agents in YAML and deploy them on AWS with zero boilerplate — built as an abstraction layer over Strands Agents SDK and Amazon Bedrock AgentCore.**

---

## The Idea

You define your agents, strategies, and workflows as YAML blueprints in your **domain repo**. This platform turns those declarations into fully operational AWS infrastructure — AgentCore Runtime containers, Gateway tool routing, Memory persistence, Identity flows, Cedar policies, observability, and multi-agent orchestration — all without writing runtime glue code.

The platform is a **bundle you deploy**: an engine that wires your domain-specific business logic into the full AgentCore stack. Domain consumers use the platform's Terraform modules + SDK + CLI to go from YAML to production.

```
Your Domain Repo                          This Platform
─────────────────                         ─────────────
blueprints/                               agent-core SDK
  agents/my-agent.yaml       ──────►      BlueprintLoader → AgentCore Runtime container
  strategies/my-strat.yaml   ──────►      StrategyBlueprint → evaluation engine
  workflows/pipeline.yaml    ──────►      Step Functions state machine
prompts/                     ──────►      PromptRegistry (versioned, mode-gated)
src/my_agents/
  agent_configs.py           ──────►      AgentConfigRegistry (prompt builders)
  mcp_registry.py            ──────►      Gateway target registration
  app.py                     ──────►      @app.entrypoint → microVM per session
```

**One handler serves every agent.** The YAML blueprint determines which model, tools, prompts, memory strategies, identity providers, and Cedar policies are wired. The domain repo only provides: prompt builders, business schemas, and domain-specific tool implementations (their own MCPs, their own Lambdas).

---

## The 12 Building Blocks

This platform is an abstraction layer over 12 AgentCore concepts. Each one maps from a YAML configuration to a fully wired AWS service. The developer declares *what*; the platform handles *how*.

### Block 1: Runtime — Where Agents Live

AgentCore Runtime hosts agents in **isolated microVMs per session**. The contract: expose `POST /invocations` + `GET /ping` on port 8080. Runtime handles scaling, warm pools, session routing, TLS, and lifecycle.

**What the platform does:** The BlueprintLoader reads the agent YAML, resolves all dependencies (model, tools, prompt, memory, hooks), and produces a Strands `Agent` wired to `@app.entrypoint`. The developer never writes the entrypoint — the platform generates it from configuration.

```yaml
# Domain repo: blueprints/agents/my-agent.yaml
runtime:
  type: agentcore          # microVM (not Lambda)
  max_iterations: 10
  idle_timeout_minutes: 15
  network_mode: PRIVATE    # VPC-only
  protocol: HTTP           # or MCP for MCP server hosting
```

```
Blueprint YAML → BlueprintLoader → AgentCoreApp(@app.entrypoint) → Docker → ECR → AgentCore Runtime → microVM
```

**Key shift from current design:** Agents are NOT Lambda functions. Lambda is for *tools* (short, stateless, fast). Agents are stateful, long-running, session-oriented — they live on Runtime. Gateway bridges them to Lambda-backed tools.

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────┐
│  Agent (microVM) │────>│   Gateway    │────>│  Lambda fn   │
│  Long-running    │     │  (MCP proxy) │     │  Short, fast │
│  Stateful        │     │              │     │  Stateless   │
│  Streaming       │     │              │     │  < 30s       │
└─────────────────┘     └──────────────┘     └──────────────┘
```

### Block 2: Gateway — The Universal Tool Bridge

Gateway is a **protocol translator** that makes any backend look like an MCP server. Agents speak MCP to Gateway; Gateway speaks whatever the backend needs (Lambda, REST, OpenAPI, Smithy, other MCP servers).

**What the platform does:** The blueprint's `tools:` section declares MCP server names. The platform registers these as Gateway targets (not direct MCP connections) and the agent consumes them through a single Gateway URL via Strands `MCPClient`.

```yaml
# Domain repo: blueprints/agents/my-agent.yaml
tools:
  - mcp: data-source-mcp     # Registered as Gateway target
    tools: [get_data, query]
  - mcp: artifacts-mcp        # Another Gateway target
    tools: [create_artifact]
```

```python
# What the platform generates (the developer never writes this):
mcp_client = MCPClient(lambda: streamablehttp_client(
    url=gateway_url,
    headers={"Authorization": f"Bearer {user_token}"}
))
with mcp_client:
    gateway_tools = mcp_client.list_tools_sync()
    agent = Agent(model=model, tools=gateway_tools)
```

**The mental model:** Agents call Gateway. Gateway routes to targets. Domain repos register their own targets (Lambdas, MCP servers, REST APIs). The agent has no idea what's behind the Gateway — it just sees MCP tools.

### Block 3: Identity — Auth Flows Through the System

Four auth patterns, all declared in YAML:

| Pattern | Use Case | YAML Key |
|---------|----------|----------|
| **Inbound JWT** | Who can call my agent? | `identity.authorizer` |
| **Outbound API Key** | Agent needs a third-party key | `identity.credentials[].type: api_key` |
| **3-Legged OAuth** | Agent needs user's Google/GitHub token | `identity.credentials[].type: oauth_3lo` |
| **M2M** | Agent-to-agent auth | `identity.credentials[].type: m2m` |

```yaml
identity:
  authorizer:
    type: cognito_jwt
    user_pool_id: ${COGNITO_POOL_ID}
    client_id: ${COGNITO_CLIENT_ID}
  credentials:
    - name: openai-key
      type: api_key
      provider: openai-apikey-provider
    - name: google-calendar
      type: oauth_3lo
      scopes: ["https://www.googleapis.com/auth/calendar.readonly"]
```

**What the platform does:** Reads the identity block, configures Runtime JWT validation, registers credential providers with AgentCore Identity, and injects `@requires_access_token` / `@requires_api_key` decorators into the generated agent code. The developer declares *which* credentials; the platform handles *how* they flow.

### Block 4: Memory — Persistence Across Sessions

AgentCore Memory provides two tiers: **short-term** (raw conversation events with TTL) and **long-term** (strategy-extracted knowledge in pgvector with semantic retrieval).

**What the platform does:** The blueprint declares memory strategies. The platform generates a Strands `HookProvider` that:
- On `AgentInitializedEvent`: loads last K turns + retrieves semantic memories → injects into system prompt
- On `MessageAddedEvent`: persists each turn to Memory service

```yaml
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
```

**Memory branching** for multi-agent pipelines: each sub-agent writes to its own branch, the coordinator reads from all branches. Declared in the workflow YAML, not coded by the developer.

### Block 5: Tools — Code Interpreter & Browser

AgentCore provides managed tools: **Code Interpreter** (sandboxed Python/Shell execution) and **Browser** (hosted Chromium with Nova Act). These are AWS-managed services — not built in this platform.

**What the platform does:** When a blueprint declares these tools, the platform registers them as Gateway targets and injects them into the agent's tool list alongside domain tools.

```yaml
tools:
  - builtin: code_interpreter
  - builtin: browser
  - mcp: my-domain-mcp
    tools: [domain_tool_1]
```

The agent sees all tools (local, Gateway, Code Interpreter, Browser) as equivalent — it doesn't know or care where they run.

### Block 6: Observability — Tracing Agent Behavior

AgentCore uses OTEL auto-instrumentation. Every LLM call, tool call, and error is traced end-to-end.

**What the platform does:** The generated Dockerfile includes `aws-opentelemetry-distro` and wraps the entrypoint with `opentelemetry-instrument`. The blueprint's `trace_attributes` flow to every span. Domain developers get full observability without writing a single line of tracing code.

```yaml
observability:
  enabled: true
  trace_attributes:
    environment: production
    agent.version: "2.1.0"
    tags: ["customer-support", "tier-1"]
  langfuse:
    enabled: true
  audit_log:
    enabled: true
    ttl_years: 5
```

```dockerfile
# Generated by platform — developer never writes this
CMD ["opentelemetry-instrument", "python", "-m", "my_agent"]
```

### Block 7: Evaluation — Measuring Agent Quality

AgentCore Evaluation reads OTEL traces and scores agent behavior with LLM-as-judge. 13 built-in evaluators + custom domain-specific judges.

**What the platform does:** The blueprint declares which evaluators to run. The platform configures online evaluation (continuous production monitoring) and on-demand evaluation (per-session scoring).

```yaml
evaluation:
  online:
    sampling_rate: 100
    evaluators:
      - Builtin.GoalSuccessRate
      - Builtin.Correctness
      - Builtin.ToolSelectionAccuracy
  custom_evaluators:
    - name: policy_compliance
      instructions: "Did the agent follow the domain policy? ..."
      scale: [1.0, 0.5, 0.0]
```

### Block 8: Policy — Cedar Access Control

Cedar policies on Gateway control who can call which tools with which parameters. Default is DENY — you explicitly permit.

**What the platform does:** The blueprint declares access rules in a simplified format. The platform generates Cedar policies and attaches them to the Gateway's policy engine.

```yaml
policy:
  engine: InsurancePolicies
  mode: ENFORCE   # or LOG_ONLY for testing
  rules:
    - name: refund_limit
      allow: process_refund
      when: "context.input.amount <= 500"
    - name: managers_only_approve
      deny: approve_claim
      unless: "principal.scope.contains('group:Managers')"
```

### Block 9: Strands Integration — The Full Stack

Strands is the primary framework because it has the deepest AgentCore integration: native `BedrockModel`, `HookProvider` for Memory, `MCPClient` for Gateway, `A2AServer` for agent-to-agent, `trace_attributes` for OTEL.

**What the platform does:** BlueprintLoader produces a fully wired Strands `Agent` with:
- `BedrockModel` configured from `model:` block
- Gateway tools via `MCPClient` from `tools:` block
- Memory `HookProvider` from `memory:` block
- Identity decorators from `identity:` block
- Observability attributes from `observability:` block
- All wrapped in `@app.entrypoint` for AgentCore Runtime

The developer declares all of this in YAML. The platform assembles it.

### Block 10: Agent-to-Agent Communication (A2A)

A2A lets agents discover and call each other via standardized protocol on port 9000. Each agent publishes an agent card at `/.well-known/agent-card.json`.

**What the platform does:** When a blueprint declares `multi_agent:` with references to other agents, the platform:
- Generates an `A2AServer` for the agent (port 9000)
- Registers M2M credential providers for cross-agent auth
- Wraps remote agent calls as Strands `@tool` functions
- The coordinator agent sees specialist agents as regular tools

```yaml
multi_agent:
  type: graph
  role: coordinator
  nodes:
    - agent_ref: search-specialist
      a2a_url: ${SEARCH_AGENT_URL}
    - agent_ref: booking-specialist
      a2a_url: ${BOOKING_AGENT_URL}
```

### Block 11: Infrastructure as Code — Terraform Modules

**Current state:** CDK stacks (8 stacks, 7 constructs).
**Target state:** Terraform modules as the primary consumable unit.

**Why Terraform:** Domain consumers use `module "agent_platform" { source = "..." }` to deploy the entire platform stack. Terraform modules are more portable, more composable, and more widely adopted than CDK across organizations.

```hcl
# Domain repo: infra/main.tf
module "platform" {
  source = "git::https://github.com/org/aws-agent-platform//modules/platform"

  environment    = "production"
  vpc_id         = module.network.vpc_id
  agents_config  = "./blueprints/agents/"
  gateway_config = "./gateway-targets.yaml"
}

module "my_domain_agents" {
  source = "git::https://github.com/org/aws-agent-platform//modules/agents"

  platform_outputs = module.platform.outputs
  blueprints_dir   = "./blueprints/"
  prompts_dir      = "./prompts/"
}
```

**The bundle concept:** You deploy an engine (this platform's Terraform modules) that reads your YAML configurations and provisions the entire AgentCore stack. The platform infrastructure is maintained separately; domain repos just consume the modules.

### Block 12: Blueprints — The Configuration Abstraction

Blueprints are the platform's core innovation: **YAML files that declare everything an agent needs, and the platform assembles it**.

Three blueprint types:

| Type | Declares | Produces |
|------|----------|----------|
| **Agent** | Model + tools + prompt + memory + identity + policy + observability | AgentCore Runtime container with full Strands agent |
| **Strategy** | Entry/exit rules, position sizing, required signals | Evaluated by strategy-evaluator agent |
| **Workflow** | Multi-agent DAG with parallel branches, choice routing, retry/catch | Step Functions state machine |

This is the platform's differentiator. Everything else (Gateway, Memory, Identity, Policy, etc.) is AWS-managed infrastructure. The blueprint layer is what turns "12 separate AWS services" into "one YAML file per agent."

---

## Platform vs. Domain — What Goes Where

| Concern | Platform (this repo) | Domain Repo |
|---------|---------------------|-------------|
| Blueprint parsing & validation | BlueprintLoader, schema validation | Blueprint YAML files |
| Agent runtime wiring | `@app.entrypoint`, `AgentCoreApp` | `app.py` (5-line handler) |
| Gateway target registration | TargetRegistry, GatewayClient | `gateway-targets.yaml` |
| Memory strategies & hooks | MemoryHookProvider generation | Memory config in blueprint YAML |
| Identity provider wiring | Decorator injection, credential resolution | Identity config in blueprint YAML |
| Cedar policy generation | CedarPolicyBuilder, Gateway attachment | Policy rules in blueprint YAML |
| Observability auto-instrumentation | Dockerfile generation, OTEL setup | `trace_attributes` in blueprint YAML |
| Evaluation configuration | Online eval setup, evaluator wiring | Evaluator selection in blueprint YAML |
| A2A server/client generation | A2AServer wrapping, M2M auth | `multi_agent` config in blueprint YAML |
| IaC deployment | Terraform modules | `module "platform" { ... }` |
| CLI tooling | `agentcli blueprint lint`, etc. | Developer runs CLI commands |
| Prompt versioning | PromptRegistry (S3 + DynamoDB) | Prompt content files |
| Prompt builders | AgentConfigRegistry interface | `agent_configs.py` (domain logic) |
| MCP server implementations | BaseMCPServer, cache, routing | Domain MCP servers |
| Domain-specific tools | — | Lambda functions, custom MCPs |
| Business schemas | — | `schemas.py` |
| Domain hooks | CompositeObservabilityHook | `hooks/constraints.py` |

---

## How a Domain Repo Consumes the Platform

### Step 1: Deploy the Platform Infrastructure

```bash
cd infra/
terraform init
terraform apply -var="environment=production"
# Outputs: gateway_url, memory_id, cognito_pool_id, ecr_repos, etc.
```

### Step 2: Install the SDK

```bash
pip install agent-core  # from CodeArtifact
```

### Step 3: Define Blueprints

```
blueprints/
  agents/
    my-agent.yaml          # All 12 blocks declared here
  strategies/
    my-strategy.yaml       # Entry/exit rules
  workflows/
    daily-pipeline.yaml    # Multi-agent DAG
```

### Step 4: Wire Domain Logic

```python
# agent_configs.py — Prompt builders (the ONLY code domain devs write per agent)
from agent_core import AgentConfig, AgentConfigRegistry

REGISTRY = AgentConfigRegistry()
REGISTRY.register(AgentConfig(
    agent_id="my-agent",
    operation_name="do_thing",
    required_fields=["date"],
    build_prompt=lambda params, idem_key: f"Do the thing for {params['date']}...",
))
```

### Step 5: Create the Handler

```python
# app.py — 5 lines, identical for every domain repo
from agent_core import BlueprintLoader, GenericHandler
HANDLER = GenericHandler(loader=BlueprintLoader(blueprints_dir="blueprints", ...))
app = AgentCoreApp(handler=HANDLER)
```

### Step 6: Deploy Domain Agents

```bash
agentcli blueprint lint blueprints/          # Validate YAML
agentcli deploy --env production             # Build → ECR → AgentCore Runtime
```

**That's it.** The platform reads the YAML, resolves all 12 blocks, builds the container, pushes to ECR, and creates the Runtime. The developer wrote: YAML blueprints + prompt builders + their own MCPs/Lambdas. Zero boilerplate.

---

## What This Unlocks

1. **New agent in 10 minutes** — Write a YAML blueprint + prompt builder. No entrypoint, no Dockerfile, no IAM roles, no Gateway config, no Memory setup.

2. **Multi-agent pipelines as YAML** — Workflows define DAGs with parallel branches, A2A communication, memory branching, and execution mode gates — all declared, not coded.

3. **Reusable infrastructure** — Deploy the platform once per account. Every domain repo (every department, every business unit) shares the same Gateway, Memory, Identity, and Observability stack.

4. **Execution mode isolation** — `EXECUTION_MODE=simulation|staging|production` routes behavior end-to-end: prompts, risk gates, data sources, execution targets.

5. **Portable across domains** — The same platform serves trading agents, customer support bots, data pipeline orchestrators, SRE agents — any domain that needs AI agents on AWS.

6. **Terraform-native consumption** — Domain repos use `module "platform" { ... }` to deploy. No CDK knowledge required. Standard Terraform workflow.

7. **Zero infrastructure knowledge** — Domain developers focus on business logic (prompts, schemas, MCPs). The platform handles all 12 AgentCore building blocks from YAML configuration.
