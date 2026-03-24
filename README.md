# AWS Agent Platform

> A configuration-driven, domain-agnostic runtime that lets you declare AI agents in YAML and deploy them on AWS with zero boilerplate — built as an abstraction layer over [Strands Agents SDK](https://github.com/strands-agents/sdk-python) and [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/).

```
Your Domain Repo                          This Platform
-----------------                         -------------
blueprints/                               agent-core SDK
  agents/my-agent.yaml       ------>      BlueprintLoader -> AgentCore Runtime container
  strategies/my-strat.yaml   ------>      StrategyBlueprint -> evaluation engine
  workflows/pipeline.yaml    ------>      Step Functions state machine
prompts/                     ------>      PromptRegistry (versioned, mode-gated)
src/my_agents/
  agent_configs.py           ------>      AgentConfigRegistry (prompt builders)
  mcp_registry.py            ------>      Gateway target registration
  app.py                     ------>      @app.entrypoint -> microVM per session
```

## What This Is

A monorepo providing the foundational runtime, tooling, and infrastructure for AI agent systems on AWS. You define your agents, strategies, and workflows as YAML blueprints in your **domain repo**. This platform turns those declarations into fully operational AWS infrastructure.

**One handler serves every agent.** The YAML blueprint determines which model, tools, prompts, memory strategies, identity providers, and Cedar policies are wired. Domain repos only provide: prompt builders, business schemas, and domain-specific tool implementations.

## Packages

| Package | Directory | Distribution | Purpose |
|---------|-----------|-------------|---------|
| `agent-core` | `core/` | CodeArtifact | Blueprint engine, runtime, hooks, schemas, observability, gateway, memory, identity, policy, evaluation, A2A, MCP base classes |
| `prompt-registry` | `prompts/` | CodeArtifact | Versioned prompt management — S3 + DynamoDB + mode-gated resolution |
| `mcp-artifacts` | `artifacts/` | Docker | Artifact store MCP server — S3 + DynamoDB + signed URLs + claim-check pattern |
| `agent-cli` | `cli/` | pip | CLI for blueprint validation, prompt management, strategy lifecycle |

## Infrastructure

| Module | Directory | Purpose |
|--------|-----------|---------|
| `platform` | `modules/platform/` | Core infra — 7 sub-modules (network, security, data, observability, api, agentcore, prompt_registry) |
| `agents` | `modules/agents/` | Per-agent deployment — blueprint-driven `for_each` over YAML |
| `workflows` | `modules/workflows/` | Step Functions from workflow YAML — parallel branches, choice routing, retry/catch |

## The 12 Building Blocks

This platform is an abstraction layer over 12 AgentCore concepts. Each maps from a YAML configuration to a fully wired AWS service.

| # | Block | What It Does |
|---|-------|-------------|
| 1 | **Runtime** | Hosts agents in isolated microVMs per session (`POST /invocations` on port 8080) |
| 2 | **Gateway** | Protocol translator — any backend (Lambda, REST, MCP, OpenAPI) looks like MCP to the agent |
| 3 | **Identity** | JWT inbound auth, API key/OAuth/M2M outbound credentials |
| 4 | **Memory** | Short-term (raw turns with TTL) + long-term (strategy-extracted knowledge in pgvector) |
| 5 | **Tools** | Managed Code Interpreter (sandboxed Python) + Browser (Chromium + Nova Act) |
| 6 | **Observability** | OTEL auto-instrumentation, CloudWatch traces, Langfuse integration |
| 7 | **Evaluation** | 12 built-in LLM-as-judge evaluators + custom domain-specific judges |
| 8 | **Policy** | Cedar access control on Gateway — default DENY, explicit PERMIT per tool |
| 9 | **Strands** | Full Strands integration: BedrockModel, HookProvider, MCPClient, A2AServer |
| 10 | **A2A** | Agent-to-agent communication via standardized protocol on port 9000 |
| 11 | **IaC** | Terraform modules as the primary consumable unit for domain repos |
| 12 | **Blueprints** | YAML declarations that wire all 12 blocks — the platform's core abstraction |

## Quick Start

### 1. Deploy the Platform

```bash
cd modules/platform
terraform init
terraform apply -var-file=envs/dev.tfvars
```

### 2. Install the SDK

```bash
pip install agent-core  # from CodeArtifact
```

### 3. Define a Blueprint

```yaml
# blueprints/agents/my-agent.yaml
id: my-agent
name: My Agent
version: "1.0.0"
prompt_ref: "my-domain/my-agent"

model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  temperature: 0.7
  max_tokens: 4096

runtime:
  type: agentcore
  network_mode: VPC
  idle_timeout_minutes: 15

tools:
  - mcp: data-service-mcp
    tools: [query_data, get_report]
  - builtin: code_interpreter

memory:
  strategies:
    - type: SEMANTIC
      name: FactExtractor
      namespace: "{actorId}/facts/"
  event_expiry_days: 30
  short_term_k: 5
```

### 4. Wire Domain Logic

```python
# agent_configs.py
from agent_core import AgentConfig, AgentConfigRegistry

REGISTRY = AgentConfigRegistry()
REGISTRY.register(AgentConfig(
    agent_id="my-agent",
    operation_name="process",
    required_fields=["date"],
    build_prompt=lambda params, key: f"Process data for {params['date']}...",
))
```

### 5. Create the Handler

```python
# app.py — identical for every domain repo
from agent_core import BlueprintLoader, GenericHandler
from agent_core.runtime.entrypoint import AgentCoreApp

app = AgentCoreApp()
HANDLER = GenericHandler(loader=BlueprintLoader(blueprints_dir="blueprints"))

@app.entrypoint
def handler(payload, context):
    return HANDLER.handle(payload, context)

if __name__ == "__main__":
    app.run()
```

### 6. Deploy

```bash
agentcli blueprint lint blueprints/agents/my-agent.yaml
agentcli deploy agent blueprints/agents/my-agent.yaml --env production
```

## How Domain Repos Consume This

```hcl
# Domain repo: infra/main.tf
module "platform" {
  source = "git::https://github.com/org/aws-agent-platform//modules/platform?ref=v1.0.0"

  environment = "production"
  vpc_id      = module.network.vpc_id
}

module "agents" {
  source = "git::https://github.com/org/aws-agent-platform//modules/agents?ref=v1.0.0"

  platform_outputs = module.platform.outputs
  blueprints_dir   = "./blueprints/"
}
```

Platform deploys FIRST. Domain repos deploy SECOND.

## Development

```bash
pip install -e "core/[dev]"       # agent-core
pip install -e "prompts/[dev]"    # prompt-registry
pip install -e "artifacts/[dev]"  # mcp-artifacts
pip install -e "cli/[dev]"        # agent-cli

# Linting
ruff check .
ruff format --check .
```

## Documentation

Full docs at [the-cloud-clock-work.github.io/tccw-aws-agent-platform](https://the-cloud-clock-work.github.io/tccw-aws-agent-platform/)

| Section | Content |
|---------|---------|
| [Getting Started](docs/getting-started.md) | Installation, quickstart, first agent tutorial |
| [Concepts](docs/concepts.md) | Mental models for each of the 12 building blocks |
| [Architecture](docs/architecture.md) | How the pieces connect, platform vs domain |
| [SDK Reference](docs/sdk.md) | API reference for all 12 subsystems |
| [Blueprints](docs/blueprints.md) | Agent, strategy, and workflow YAML specs |
| [Infrastructure](docs/infrastructure.md) | Terraform module reference |
| [CLI](docs/cli.md) | Command reference for `agentcli` |

## AWS Configuration

| Setting | Value |
|---------|-------|
| Primary Region | `eu-west-1` |
| Bedrock Region | `us-west-2` |
| CodeArtifact Domain | `platform` |
| CodeArtifact Repo | `platform-python` |

## License

Proprietary.
