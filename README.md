# AWS Agent Platform

> A configuration-driven, domain-agnostic runtime that lets you declare AI agents in YAML and deploy them on AWS with zero boilerplate — built as an abstraction layer over [Strands Agents SDK](https://github.com/strands-agents/sdk-python) and [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/).

> **Status (Apr 2026):** 92/100 production readiness. Phase 1 (provider-agnostic inference) + Phase 2 (observability decoupling) shipped and validated in production via `pilot-t6-1775766858` (16/16 Step Functions states SUCCEEDED, end-to-end, empty-gaps path). Bedrock is **no longer required for inference** — the loader dispatches across `bedrock | anthropic | litellm | vertex` per blueprint, and all 9 QITP agents run on LiteLLM-proxied `claude-sonnet-4-6`. Stage 3 (standalone runtime / ECS Fargate / memory optionality) is **postponed** — the current decoupling is sufficient. See `operator/inference-migration.md` for detail.

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

### 0. Create a Domain Repo

```bash
bash <(curl -sL https://raw.githubusercontent.com/The-Cloud-Clock-Work/tccw-aws-agent-platform/main/scripts/create-domain.sh)
```

This scaffolds a complete domain repo with agents, MCPs, lambdas, and Terraform — ready for `terraform init`. See [Domain Repo Guide](#domain-repo-guide) for the full structure reference.

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
  # Provider is dispatched in loader: bedrock | anthropic | litellm | vertex.
  # LiteLLM is the current production path for multi-model (Claude/Gemini/GPT) inference.
  provider: litellm
  model_id: claude-sonnet-4-6
  base_url: https://llm.example.com
  api_key_env: LITELLM_API_KEY
  extra_headers_env:
    CF-Access-Client-Id: CF_ACCESS_CLIENT_ID
    CF-Access-Client-Secret: CF_ACCESS_CLIENT_SECRET
  # temperature / max_tokens intentionally omitted — set per-blueprint, never hardcoded.

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

## Domain Repo Guide

Domain-specific repos consume this platform by following a **convention-driven folder structure**. The Terraform modules, build scripts, and SDK all rely on specific directory layouts and naming patterns. This section documents every convention.

### Required Folder Structure

```
my-domain-repo/
├── agents/                            # Agent runtimes (monorepo layout)
│   ├── Dockerfile                     # Shared container image for all agents
│   ├── pyproject.toml                 # Python package (depends on agent-core)
│   ├── src/my_domain_agents/          # Domain agent source code
│   │   ├── app.py                     # Entrypoint — identical across domains
│   │   ├── agent_configs.py           # AgentConfigRegistry + prompt builders
│   │   └── ...
│   ├── blueprints/
│   │   ├── agents/                    # One YAML per agent runtime
│   │   │   ├── my-agent.yaml
│   │   │   └── another-agent.yaml
│   │   ├── strategies/                # Evaluation strategy YAMLs
│   │   │   └── my-strategy.yaml
│   │   └── workflows/                 # Step Functions workflow YAMLs
│   │       └── my-pipeline.yaml
│   └── prompts/
│       └── my-domain/                 # Prompt text files (namespace = prompt_ref prefix)
│           ├── my-agent.txt
│           └── another-agent.txt
├── mcps/                              # MCP servers (polyrepo layout)
│   ├── blueprints/                    # One YAML per MCP server
│   │   ├── data-service-mcp.yaml
│   │   └── another-mcp.yaml
│   ├── data-service/                  # Per-MCP subdirectory (name = blueprint ID minus suffix)
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   ├── src/
│   │   └── tests/
│   └── another/
│       ├── Dockerfile
│       └── ...
├── lambdas/                           # Lambda functions (domain-managed)
│   ├── my-function/
│   │   └── handler.py
│   └── stubs/                         # Placeholder handlers for workflow steps
│       └── handler.py
├── infra/                             # Terraform — consumes platform modules
│   ├── main.tf                        # 3 module calls: platform, agents, mcps, workflows
│   ├── variables.tf
│   ├── providers.tf
│   ├── backend.tf
│   ├── envs/
│   │   ├── dev.tfvars
│   │   ├── staging.tfvars
│   │   └── production.tfvars
│   ├── domain_*.tf                    # Domain-specific resources (DynamoDB, Lambda, etc.)
│   └── scripts/                       # Domain infra helper scripts
├── scripts/                           # Domain automation scripts
└── pyproject.toml                     # Root-level dev tooling (ruff, mypy)
```

### Agents — Monorepo Layout

All agents share a **single Docker image**. The YAML blueprint determines behavior at runtime.

| Convention | Expected By |
|-----------|-------------|
| `agents/Dockerfile` at root | `build-runtime.sh` — fails if missing |
| `agents/pyproject.toml` | Zipped into CodeBuild source |
| `agents/src/` | Zipped into CodeBuild source |
| `agents/blueprints/` | Zipped into image + loaded by `BlueprintLoader` |
| `agents/prompts/` | Zipped into image (optional, for local prompt fallback) |

**Terraform wiring:**

```hcl
module "agents" {
  source = "git::https://github.com/org/aws-agent-platform//modules/agents?ref=v1.0.0"

  blueprint_dir  = "${path.module}/../agents/blueprints/agents"
  source_dir     = "${path.root}/../agents"
  source_layout  = "monorepo"              # Single shared Dockerfile
  build_enabled  = var.build_enabled
  # ... platform outputs wired from module.platform.*
}
```

**The `app.py` entrypoint is identical for every domain:**

```python
from agent_core import BlueprintLoader
from agent_core.runtime.entrypoint import AgentCoreApp

app = AgentCoreApp()
loader = BlueprintLoader("blueprints", prompt_dir="prompts")

@app.entrypoint
def handler(payload, context):
    return loader.build_entrypoint(payload["agent_id"])

if __name__ == "__main__":
    app.run()
```

**Build flow:** `terraform apply -var="build_enabled=true"` triggers `build-runtime.sh` which:
1. Zips `Dockerfile`, `pyproject.toml`, `src/`, `blueprints/`, `prompts/`
2. Uploads to S3 (`codebuild_source_bucket`)
3. Triggers CodeBuild with `sourceLocationOverride` (NO_SOURCE pattern)
4. CodeBuild authenticates to CodeArtifact, builds ARM64 image, pushes to ECR

### MCP Servers — Polyrepo Layout

Each MCP server has its **own subdirectory with its own Dockerfile**.

| Convention | Expected By |
|-----------|-------------|
| `mcps/blueprints/` contains `*.yaml` | Terraform `fileset()` for `for_each` |
| Blueprint `id` field ends with configured suffix (default: `-mcp`) | `build-runtime.sh` strips suffix to find subdir |
| `mcps/{name}/Dockerfile` | `build-runtime.sh` — fails if missing |

**Name derivation:** The build system strips `polyrepo_suffix` from the blueprint ID to find the subdirectory:
- Blueprint ID `data-service-mcp` with suffix `-mcp` → looks for `mcps/data-service/Dockerfile`

**Terraform wiring:**

```hcl
module "mcps" {
  source = "git::https://github.com/org/aws-agent-platform//modules/agents?ref=v1.0.0"

  resource_prefix  = "${var.resource_prefix}-mcp"    # Distinguish from agent resources
  blueprint_dir    = "${path.module}/../mcps/blueprints"
  source_dir       = "${path.root}/../mcps"
  source_layout    = "polyrepo"                       # Per-service Dockerfiles
  polyrepo_suffix  = "-mcp"                           # Strip to find subdir name
  build_enabled    = var.build_enabled

  # Shared code injection (optional)
  extra_build_deps = {
    "my-mcp" = "shared-lib:deps/shared-lib"           # src_path:zip_path
  }
}
```

### Lambdas

Lambda functions are **not managed by platform modules** — the domain's `infra/` declares `aws_lambda_function` resources directly.

Lambdas integrate with the platform through **workflow blueprints**:
- Workflow YAML references functions via `lambda_ref: my-function`
- `infra/main.tf` passes `lambda_arns = { "my-function" = aws_lambda_function.my_fn.arn }` to the workflows module

Convention: one directory per function under `lambdas/`. A `stubs/` directory holds placeholder handlers for workflow steps not yet implemented.

### Infrastructure (infra/)

The `infra/` directory makes **three to four module calls** in dependency order:

```
platform  →  agents  →  workflows
              mcps  ↗
```

```hcl
# 1. Platform foundation (VPC, KMS, DynamoDB, Gateway, Memory, API)
module "platform" {
  source = "git::https://github.com/org/aws-agent-platform//modules/platform?ref=v1.0.0"
  environment     = var.environment
  resource_prefix = var.resource_prefix
  # ...
}

# 2a. Agent runtimes (depends on platform)
module "agents" {
  source     = "git::https://github.com/org/aws-agent-platform//modules/agents?ref=v1.0.0"
  depends_on = [module.platform]

  blueprint_dir           = "${path.module}/../agents/blueprints/agents"
  gateway_id              = module.platform.gateway_id
  gateway_url             = module.platform.gateway_url
  memory_id               = module.platform.memory_id
  vpc_id                  = module.platform.vpc_id
  private_subnet_ids      = module.platform.private_subnet_ids
  agent_security_group_id = module.platform.agent_security_group_id
  # ... remaining platform outputs
}

# 2b. MCP runtimes (depends on platform, uses same agents module)
module "mcps" {
  source     = "git::https://github.com/org/aws-agent-platform//modules/agents?ref=v1.0.0"
  depends_on = [module.platform]

  resource_prefix         = "${var.resource_prefix}-mcp"
  blueprint_dir           = "${path.module}/../mcps/blueprints"
  source_layout           = "polyrepo"
  polyrepo_suffix         = "-mcp"
  # ... same platform outputs
}

# 3. Workflows (depends on agents for runtime ARNs)
module "workflows" {
  source     = "git::https://github.com/org/aws-agent-platform//modules/workflows?ref=v1.0.0"
  depends_on = [module.agents]

  workflow_dir       = "${path.module}/../agents/blueprints/workflows"
  agent_runtime_arns = module.agents.runtime_arns
  lambda_arns        = { "my-fn" = aws_lambda_function.my_fn.arn }
}
```

**Domain-specific resources** go in `domain_*.tf` files (e.g., `domain_data.tf` for DynamoDB tables, `domain_lambdas.tf` for Lambda functions).

### Blueprint Conventions

Blueprints are the platform's core abstraction. Both Terraform and the SDK rely on these conventions:

| Rule | Enforced By |
|------|-------------|
| Files must be `*.yaml` (not `.yml` for Terraform) | `fileset(dir, "*.yaml")` in `locals.tf` |
| Each file must have a top-level `id` field | Terraform `yamldecode().id` for `for_each` key |
| The `id` is used for all resource naming | ECR repos, CodeBuild projects, IAM roles, runtimes |
| Agent blueprints live in `blueprints/agents/` | `BlueprintLoader._find_yaml("agents", id)` |
| Strategy blueprints live in `blueprints/strategies/` | `BlueprintLoader._find_yaml("strategies", id)` |
| Workflow blueprints live in `blueprints/workflows/` | `BlueprintLoader._find_yaml("workflows", id)` |

The SDK's `BlueprintLoader` accepts both `.yaml` and `.yml` extensions and also falls back to scanning by `id` field. Terraform's `fileset()` only matches `*.yaml`.

### Build System

Builds are triggered by Terraform and executed by CodeBuild:

```bash
# Build all agents/MCPs
terraform apply -var="build_enabled=true"

# Build a single service
terraform apply -var="build_enabled=true" -var='build_services={"my-agent":true}'
```

The `build-runtime.sh` script (embedded in the agents module) handles:
1. **Zip** — source code into a temporary archive
2. **Upload** — zip to S3 (`codebuild_source_bucket`)
3. **Trigger** — CodeBuild with `--source-type-override S3 --source-location-override`
4. **Poll** — wait for build completion

CodeBuild projects authenticate to CodeArtifact automatically via the inline buildspec, so `agent-core` (and any other platform packages) resolve during `pip install`.

### Observability

The platform includes `observe-runtime.sh` for runtime monitoring:

```bash
# Summary table of all runtimes
./modules/agents/scripts/observe-runtime.sh

# Filter by type
./modules/agents/scripts/observe-runtime.sh --agents
./modules/agents/scripts/observe-runtime.sh --mcps

# Drill into a specific runtime
./modules/agents/scripts/observe-runtime.sh my-agent --logs
./modules/agents/scripts/observe-runtime.sh my-agent --traces
./modules/agents/scripts/observe-runtime.sh my-agent --metrics
./modules/agents/scripts/observe-runtime.sh my-agent --all
```

Log groups follow the pattern: `/aws/bedrock-agentcore/runtimes/{runtime-short-name}`

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
