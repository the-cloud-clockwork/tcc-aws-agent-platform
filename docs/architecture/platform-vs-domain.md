---
title: Platform vs. Domain
nav_order: 2
parent: Architecture
grand_parent: Documentation
---

# Platform vs. Domain

The platform and domain repos have a clear, enforced separation of concerns. Understanding this boundary is essential before writing any agent code.

---

## The Core Idea

The platform is a **bundle you deploy**: an engine that wires your domain-specific business logic into the full AgentCore stack. The platform knows nothing about what your agents do. Your domain repos know nothing about how AgentCore is wired.

```
Your Domain Repo                          This Platform
-----------------                         -------------
blueprints/                               agent-core SDK
  agents/my-agent.yaml       ------►      BlueprintLoader → AgentCore Runtime container
  strategies/my-strat.yaml   ------►      StrategyBlueprint → evaluation engine
  workflows/pipeline.yaml    ------►      Step Functions state machine
prompts/                     ------►      PromptRegistry (versioned, mode-gated)
src/my_domain/
  agent_configs.py           ------►      AgentConfigRegistry (prompt builders)
  mcp_registry.py            ------►      Gateway target registration
  app.py                     ------►      @app.entrypoint → microVM per session
```

---

## Responsibility Matrix

| Concern | Platform (this repo) | Domain Repo |
|---------|---------------------|-------------|
| Blueprint parsing and validation | `BlueprintLoader`, schema validation | Blueprint YAML files |
| Agent runtime wiring | `@app.entrypoint`, `AgentCoreApp` | `app.py` (5-line handler) |
| Gateway target registration | `TargetRegistry`, `GatewayClient` | `gateway-targets.yaml` |
| Memory strategies and hooks | `MemoryHookProvider` generation | Memory config in blueprint YAML |
| Identity provider wiring | Decorator injection, credential resolution | Identity config in blueprint YAML |
| Cedar policy generation | `CedarPolicyBuilder`, Gateway attachment | Policy rules in blueprint YAML |
| Observability auto-instrumentation | Dockerfile generation, OTEL setup | `trace_attributes` in blueprint YAML |
| Evaluation configuration | Online eval setup, evaluator wiring | Evaluator selection in blueprint YAML |
| A2A server and client generation | `A2AServer` wrapping, M2M auth | `multi_agent` config in blueprint YAML |
| IaC deployment | Terraform modules | `module "platform" { ... }` |
| CLI tooling | `agentcli blueprint lint`, etc. | Developer runs CLI commands |
| Prompt versioning | `PromptRegistry` (S3 + DynamoDB) | Prompt content files |
| Prompt builders | `AgentConfigRegistry` interface | `agent_configs.py` (domain logic) |
| MCP server implementations | `BaseMCPServer`, cache, routing | Domain MCP servers |
| Domain-specific tools | — | Lambda functions, custom MCPs |
| Business schemas | — | `schemas.py` |
| Domain hooks | `CompositeObservabilityHook` interface | `hooks/constraints.py` |

---

## The Contract

The platform provides three things:

1. **SDK** (`agent-core`) — runtime engine, blueprint loader, all client classes
2. **Terraform modules** — infrastructure for Gateway, Memory, Identity, Observability, data stores
3. **CLI** (`agent-cli`) — blueprint validation, deployment, prompt management

Domain repos provide three things:

1. **Blueprint YAML** — declares model, tools, memory, identity, policy, observability per agent
2. **Prompt builders** — domain-specific `AgentConfigRegistry` implementations
3. **Tool implementations** — Lambda functions and custom MCP servers containing business logic

Everything else is handled by the platform.

---

## Directory Structure Comparison

### Platform Repo

```
aws-agent-platform/
+-- core/                      # agent-core SDK — 15 subsystems
|   +-- src/agent_core/
|       +-- runtime/           # AgentCoreApp, GenericHandler, SessionManager
|       +-- gateway/           # GatewayClient, TargetRegistry, ToolDiscovery
|       +-- memory/            # MemoryManager, MemoryHookProvider
|       +-- identity/          # IdentityProvider, IdentityClient
|       +-- observability/     # LangfuseHook, AuditLogWriter, XRayTracer
|       +-- evaluation/        # EvaluationClient, BuiltinEvaluators
|       +-- policy/            # PolicyClient, CedarPolicyBuilder
|       +-- blueprints/        # BlueprintLoader, AgentBlueprint, AgentSession
|       +-- a2a/               # A2AServerWrapper, A2AClient, A2AWiring
|       +-- schemas/           # AgentBlueprint, StrategyBlueprint, WorkflowBlueprint
|       +-- mcp/               # BaseMCPServer, cache, routing
+-- prompts/                   # prompt-registry service
+-- artifacts/                 # mcp-artifacts MCP server
+-- cli/                       # agent-cli tooling
+-- modules/                   # Terraform infrastructure
    +-- platform/              # Core infra (6 sub-modules)
    +-- agents/                # Per-agent deployment
    +-- workflows/             # Step Functions from YAML
```

### Domain Repo

```
my-domain-repo/
+-- blueprints/                # Blueprint YAML — consumed by platform SDK
|   +-- agents/
|   |   +-- my-agent.yaml      # Declares all 12 blocks
|   +-- strategies/
|   |   +-- my-strategy.yaml
|   +-- workflows/
|       +-- pipeline.yaml
+-- prompts/                   # Prompt content files — managed by PromptRegistry
|   +-- my-agent/
|       +-- system-prompt.txt
+-- src/
|   +-- my_domain/
|       +-- agent_configs.py   # Prompt builders — the ONLY runtime code domain devs write
|       +-- mcp_registry.py    # Gateway target registration
|       +-- app.py             # 5-line handler, identical for every domain repo
|       +-- schemas.py         # Business data schemas
+-- mcps/                      # Domain MCP server implementations
|   +-- data-tools/
|       +-- server.py
+-- lambdas/                   # Domain Lambda functions (tools for agents)
|   +-- data-tools/
|       +-- handler.py
+-- infra/                     # Terraform — consumes platform modules
    +-- main.tf
    +-- envs/
        +-- dev.tfvars
        +-- production.tfvars
```

---

## What Domain Developers Actually Write

### The Handler (identical for every agent)

```python
# app.py — every domain repo, every agent
from agent_core import AgentCoreApp, BlueprintLoader, GenericHandler

HANDLER = GenericHandler(
    loader=BlueprintLoader(blueprints_dir="blueprints", config_registry=REGISTRY)
)
app = AgentCoreApp(handler=HANDLER)
```

Five lines. The blueprint drives all behavior.

### The Prompt Builder (unique per agent)

```python
# agent_configs.py — the only domain-specific runtime code
from agent_core import AgentConfig, AgentConfigRegistry

REGISTRY = AgentConfigRegistry()

REGISTRY.register(AgentConfig(
    agent_id="my-agent",
    operation_name="process",
    required_fields=["input_data"],
    build_prompt=lambda params, idem_key: (
        f"[Task: {idem_key}]\n\nProcess the following: {params['input_data']}"
    ),
))
```

The prompt builder is the only code domain developers write per agent. It constructs the system prompt from business parameters. Everything else — model selection, tool wiring, memory injection, identity decorators — is handled by the platform from the blueprint YAML.

---

## Why This Separation Matters

**Reusability.** Deploy the platform once per account. Every department, every business unit, every domain repo shares the same Gateway, Memory, Identity, and Observability stack.

**Zero boilerplate.** Domain developers focus on business logic (prompts, schemas, tool implementations). They never write runtime wiring, Dockerfiles, IAM policies, or AgentCore API calls.

**Portability.** The same platform serves agents in any domain — customer support, data analysis, SRE automation, content generation — because it is domain-agnostic by design.

**Zero domain contamination.** The platform repo must never contain domain-specific terms. This is enforced by `scripts/domain-scan.sh`. The separation is not just architectural — it is tested in CI.

---

## How a Domain Repo Consumes the Platform

The full consumption flow in six steps, from infrastructure deployment to a live agent.

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
    my-strategy.yaml       # Trigger conditions, parameters
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
agentcli deploy --env production             # Build -> ECR -> AgentCore Runtime
```

**That's it.** The platform reads the YAML, resolves all 12 blocks, builds the container, pushes to ECR, and creates the Runtime. The developer wrote: YAML blueprints + prompt builders + their own MCPs/Lambdas. Zero boilerplate.

---

## What This Unlocks

1. **New agent in 10 minutes** — Write a YAML blueprint + prompt builder. No entrypoint, no Dockerfile, no IAM roles, no Gateway config, no Memory setup.

2. **Multi-agent pipelines as YAML** — Workflows define DAGs with parallel branches, A2A communication, memory branching, and execution mode gates — all declared, not coded.

3. **Reusable infrastructure** — Deploy the platform once per account. Every domain repo (every department, every business unit) shares the same Gateway, Memory, Identity, and Observability stack.

4. **Execution mode isolation** — `EXECUTION_MODE=simulation|staging|production` routes behaviour end-to-end: prompts, data sources, execution targets.

5. **Portable across domains** — The same platform serves any domain that needs AI agents on AWS — customer support, data analysis, SRE automation, content generation.

6. **Terraform-native consumption** — Domain repos use `module "platform" { ... }` to deploy. No CDK knowledge required. Standard Terraform workflow.

7. **Zero infrastructure knowledge** — Domain developers focus on business logic (prompts, schemas, MCPs). The platform handles all 12 AgentCore building blocks from YAML configuration.

---

## Next Steps

- [How It Works]({{ '/docs/architecture/how-it-works' | relative_url }}) — end-to-end flows showing the platform and domain repos interacting
- [The 12 Building Blocks]({{ '/docs/architecture/building-blocks' | relative_url }}) — each concern in the responsibility matrix explained in depth
- [Blueprints]({{ '/docs/blueprints/' | relative_url }}) — the YAML specification that defines the domain/platform interface
