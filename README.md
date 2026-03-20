# AWS Agent Platform

A generic, domain-agnostic runtime for building AI agent systems on AWS. Provides the foundational infrastructure — blueprint engine, execution modes, observability, MCP server toolkit, prompt versioning, artifact storage, and CDK stacks — so domain-specific repos can focus purely on business logic.

Think of it as **your own Bedrock AgentCore**: a runner that knows how to execute agents, manage sessions, route by execution mode, track costs, enforce idempotency, and deploy infrastructure — but has zero knowledge of what those agents actually do.

## Why This Exists

Building AI agent systems requires solving the same infrastructure problems every time: how agents load configuration, how they connect to tools, how outputs flow through Step Functions without hitting payload limits, how prompts get versioned without hardcoding, how you trace a request across Lambda → ECS → Bedrock. This platform solves all of that once, so every new domain (trading, customer support, data pipelines) inherits it for free.

**The separation is strict**: this repo passes a domain contamination scanner (`domain-scan.sh`) with zero hits. It has never heard of your business domain and never will.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Domain Repos                                                │
│  Your agents, MCPs, risk engines, workflows, dashboards      │
│  pip install agent-core  ←── from CodeArtifact               │
├──────────────────────────────────────────────────────────────┤
│  AWS Agent Platform (this repo)                              │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ agent-core  │  │ prompt-      │  │ mcp-artifacts      │  │
│  │ SDK library │  │ registry     │  │ MCP server         │  │
│  │ 48 exports  │  │ versioned    │  │ S3 + signed URLs   │  │
│  │ 15 systems  │  │ prompt mgmt  │  │ claim-check        │  │
│  └─────────────┘  └──────────────┘  └────────────────────┘  │
│  ┌─────────────┐  ┌──────────────────────────────────────┐  │
│  │ agent-cli   │  │ agent-infra (CDK)                    │  │
│  │ dev tooling │  │ 8 stacks · 7 constructs · 3 envs    │  │
│  │ blueprint   │  │ VPC · Lambda · ECS · SFN · DDB · S3 │  │
│  │ validation  │  │ KMS · API GW · CloudWatch · X-Ray   │  │
│  └─────────────┘  └──────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  AWS Services                                                │
│  Lambda · ECS Fargate · Step Functions · DynamoDB · S3       │
│  Bedrock · CodeArtifact · KMS · API Gateway · CloudWatch     │
└──────────────────────────────────────────────────────────────┘
```

**Deployment model:** Platform deploys first → creates VPC, ECS cluster, DynamoDB tables, S3 buckets, Lambda layers, service discovery. Domain repos deploy second → read platform SSM parameters, plug in their own agents/MCPs/workflows on top.

## Modules

### `core/` — Agent Core SDK

**Package:** `agent-core` · **Version:** 0.7.0 · **Published to:** AWS CodeArtifact

The library every agent imports. Provides 48 public exports across 15 subsystems:

| Subsystem | What It Does |
|-----------|-------------|
| **Blueprints** | Load YAML agent/strategy/workflow definitions → Pydantic models → fully-configured Strands agents |
| **Execution Modes** | Route behavior by `EXECUTION_MODE` env var (simulation / staging / production) |
| **Runtime** | Universal Lambda handler (`GenericHandler`), session management, payload normalization (Lambda ↔ AgentCore) |
| **Idempotency** | DynamoDB-backed idempotency keys with 24h TTL on all write operations |
| **Observability** | Pluggable hooks: Langfuse (prompt tracking), X-Ray (distributed tracing), CloudWatch (metrics), audit log (DynamoDB, 5-year retention), cost tracking, SNS alerts |
| **MCP Toolkit** | `BaseMCPServer` base class, Redis cache, execution mode routing, versioned S3 store — shared infrastructure for all MCP servers |
| **Gateway** | AgentCore Gateway client — tool discovery, target registration, semantic search |
| **Memory** | Three-tier memory manager (short/long/episodic) with session bridging |
| **Identity** | OAuth/OIDC provider abstraction for external service auth |
| **Policy** | Cedar policy builder — generate `.cedar` files from Python dataclasses |
| **Prompt Client** | HTTP client for the Prompt Registry API |
| **Tool Factory** | Dynamic MCP client instantiation from blueprint YAML |
| **Schemas** | `ModelConfig`, `ToolConfig`, `RuntimeConfig` — typed configuration |
| **Multi-tenant** | Tenant isolation + memory branching for shared infrastructure |
| **Streaming** | AgentCore streaming response support |

<details>
<summary>Full public API (48 exports)</summary>

```python
from agent_core import (
    # Blueprints
    AgentBlueprint, StrategyBlueprint, WorkflowBlueprint,
    BlueprintLoader, BlueprintLoadError, AgentSession,
    StrategyEvaluator, WorkflowExecutor,
    GraphNodeConfig, GraphEdgeConfig,
    # Execution
    ExecutionMode, get_execution_mode, validate_agent_mode,
    # Runtime
    GenericHandler, AgentConfig, AgentConfigRegistry,
    AgentCoreApp, register_agent,
    AgentPayload, AgentResult, RuntimeMode, normalize_payload,
    SessionManager, SessionState, StrandsSessionBridge,
    IdempotencyStore, generate_idempotency_key,
    marshal_output,
    # Observability
    ObservabilityHook, CompositeObservabilityHook, create_observability_hooks,
    AuditLogWriter, StructuredLogger, LogSchema,
    CostTracker, LangfuseHook, XRayTracer, AlertPublisher,
    # Prompt
    PromptRegistryClient, PromptResolutionError,
    # MCP
    BaseMCPServer, VersionedS3Store,
    cache_get, cache_set, resolve_provider,
    # Tools
    create_mcp_client,
)
```
</details>

### `prompts/` — Prompt Registry

**Package:** `prompt-registry` · **Version:** 0.1.0 · **Published to:** AWS CodeArtifact

Versioned prompt management service. Enforces a hard rule: **zero hardcoded prompts** in agent code.

| Operation | Route | Description |
|-----------|-------|-------------|
| Create | `POST /prompts` | Upload new version (starts as DRAFT) |
| Resolve | `GET /prompts/{id}` | Get latest STABLE version (or pinned) |
| List | `GET /prompts/{id}/versions` | All versions with status |
| Promote | `POST /prompts/{id}/promote` | DRAFT → STABLE |
| Rollback | `POST /prompts/{id}/rollback` | Revert to specific version |
| Diff | `GET /prompts/{id}/diff` | Unified diff between versions |

**Mode-gated access:** Production only resolves STABLE prompts. Dev/simulation can use DRAFT.

**Storage:** S3 for prompt content (`{prompt_id}/{version}.txt`), DynamoDB for metadata.

### `artifacts/` — Artifacts MCP Server

**Package:** `mcp-artifacts` · **Version:** 0.1.0 · **Runs on:** Docker / ECS Fargate

Universal output pipeline implementing the **claim-check pattern** — all agent outputs stored in S3, only S3 keys flow through Step Functions (256KB payload limit).

| Tool | Purpose |
|------|---------|
| `create_artifact` | Upload content to S3 + register in DynamoDB catalog |
| `get_artifact` | Retrieve metadata + pre-signed download URL (1h expiry) |
| `poll_artifact` | Async polling loop (2s interval) until artifact is ready |
| `list_artifacts` | Query by type, agent, or date range (GSI-backed) |

**Artifact types:** chart (JSX), report (Markdown), analysis_result (JSON), recommendation (JSON), image (PNG), data_export (CSV).

**Idempotency:** Duplicate writes prevented via `idempotency_key` field.

### `cli/` — Agent CLI

**Package:** `agent-cli` · **Version:** 0.1.0 · **Entry point:** `agentcli`

Developer tooling for blueprint validation, prompt management, strategy lifecycle, and multi-agent topology visualization.

```bash
agentcli blueprint lint agents/my_agent.yaml       # Validate YAML schema
agentcli prompt push prompts/sys.txt --id sys_v2    # Upload to registry
agentcli prompt diff sys_prompt 1.0.0 2.0.0         # Compare versions
agentcli strategy validate strategies/momentum.yaml # Check strategy schema
agentcli graph render agents/evaluator.yaml         # ASCII topology diagram
```

### `infra/` — CDK Infrastructure

**Package:** `agent-infra` · **Version:** 0.2.0 · **CDK:** Python

8 stacks + 7 reusable constructs. **Entirely configuration-driven** — all resource names, table schemas, bucket names, and service definitions come from `config/{env}.yaml`. The same stack code deploys across dev / staging / production with zero code changes.

| Stack | What It Creates |
|-------|----------------|
| `DataStack` | DynamoDB tables (artifacts, audit_log, prompt_registry, run_history, idempotency) + S3 buckets |
| `NetworkStack` | VPC with 3-tier subnets (public/private/isolated) + NAT gateways + security groups |
| `SecurityStack` | KMS customer-managed keys + Secrets Manager + WAF WebACL + VPC endpoints |
| `AgentStack` | Lambda functions + Strands SDK layer + least-privilege IAM roles |
| `McpStack` | ECS Fargate cluster + Cloud Map service discovery + ECR repositories |
| `ObservabilityStack` | CloudWatch dashboard + SNS alert topic + X-Ray tracing group |
| `ApiStack` | API Gateway with throttling + CORS + Lambda integration |
| `WorkflowStack` | Step Functions state machine templates |

**Reusable constructs:**

| Construct | Purpose |
|-----------|---------|
| `McpServiceConstruct` | ECR repo + Fargate service + service discovery registration (one per MCP) |
| `StrandsAgentTask` | Lambda wrapper with claim-check pattern for Step Functions integration |
| `SfnWorkflow` | YAML blueprint → Step Functions state machine (auto-generates ASL) |
| `FargateAutoScaling` | CPU-based target tracking for Fargate services |
| `LambdaProvisionedConcurrency` | Provisioned concurrency for latency-sensitive agents |
| `WafWebAcl` | WAF rules with rate limiting + IP allowlist |
| `VpcEndpointsConstruct` | Private connectivity to AWS services (S3, DynamoDB, Bedrock, etc.) |

**Cross-stack references via SSM:**
```
/platform/{env}/tables/{name}/name
/platform/{env}/buckets/{name}/name
/platform/{env}/agents/{name}/arn
/platform/{env}/mcps/{name}/endpoint
/platform/{env}/security/{key}/arn
/platform/{env}/alert-topic-arn
```

**Environment profiles:**

| Setting | Dev | Staging | Production |
|---------|-----|---------|------------|
| DynamoDB billing | On-demand | On-demand | Provisioned |
| NAT gateways | 1 | 1 | 2 |
| WAF | Off | On | On |
| Lambda concurrency | 0 (unreserved) | 5 | 50+ |
| S3 tiering | Off | Off | Intelligent |
| Log retention | 14 days | 90 days | 365 days |

## Quick Start

```bash
# Prerequisites: Python 3.12+, Node.js 20+ (CDK), AWS CLI configured
git clone https://github.com/The-Cloud-Clock-Work/tccw-aws-agent-platform.git
cd tccw-aws-agent-platform

# Create virtualenv
python3.12 -m venv .venv && source .venv/bin/activate

# Install agent-core (the SDK)
pip install -e "core/[dev]"

# Install all modules
pip install -e "core/[dev]" -e "prompts/[dev]" -e "artifacts/[dev]" -e "cli/[dev]" -e "infra/[dev]"

# Lint
ruff check .

# Deploy infrastructure (dev environment)
cd infra
cdk synth -c env=dev
cdk deploy -c env=dev
```

## CI/CD

### GitHub Actions

| Workflow | Trigger | What It Does |
|----------|---------|-------------|
| `ci-core.yml` | `core/**` changes on push/PR | pytest + ruff + mypy |
| `ci-prompts.yml` | `prompts/**` changes | pytest + ruff |
| `ci-artifacts.yml` | `artifacts/**` changes | pytest + ruff |
| `ci-cli.yml` | `cli/**` changes | pytest + ruff |
| `ci-infra.yml` | `infra/**` changes | pytest + ruff + cdk synth |
| `publish.yml` | `v*` tags | Build wheel + publish to CodeArtifact |
| `sonar-scan.yml` | Push/PR to main | Multi-module SonarQube analysis |

Path-filtered: changing `core/` only runs `ci-core.yml`. No wasted CI minutes.

### CodeArtifact

Private PyPI registry for cross-repo package sharing.

| Setting | Value |
|---------|-------|
| Domain | `platform` |
| Repository | `platform-python` |
| Region | `eu-west-1` |
| Upstream | PyPI (public) |

Published packages: `agent-core`, `prompt-registry`. Domain repos install them with:

```bash
pip install agent-core --extra-index-url https://${CODEARTIFACT_TOKEN}@platform-123456789012.d.codeartifact.eu-west-1.amazonaws.com/pypi/platform-python/simple/
```

### SonarQube

Multi-module project: `aws-agent-platform` with 5 sub-modules (core, prompts, artifacts, cli, infra). Scanned on every push to `main`.

## Domain Isolation

This platform is **domain-agnostic by design and by enforcement**.

A domain contamination scanner (`scripts/domain-scan.sh`) checks for trading terms, broker references, regulatory language, and domain-specific identifiers. It runs in CI and must return **zero HARD-term hits**. Any domain-specific logic — agents, MCP servers, risk engines, regulatory compliance, workflows — belongs in a domain repo, not here.

The allowed dependency direction:
```
domain repo  →  imports  →  agent-core (this repo)
domain repo  →  reads    →  platform SSM parameters (this repo's CDK output)
this repo    →  NEVER    →  imports domain packages
```

## AWS Configuration

| Setting | Value |
|---------|-------|
| Account | `123456789012` |
| Primary Region | `eu-west-1` |
| Bedrock Region | `us-west-2` |
| Default Model | `us.anthropic.claude-sonnet-4-20250514-v1:0` |
| CDK Bootstrap | `cdk bootstrap aws://123456789012/eu-west-1` |

## Repository Structure

```
tccw-aws-agent-platform/
├── core/                          # agent-core SDK
│   ├── src/agent_core/            # 15 subsystems, 64 source files
│   │   ├── blueprints/            # YAML → Pydantic → Strands agent
│   │   ├── execution/             # Execution mode routing
│   │   ├── runtime/               # Lambda handler, sessions, idempotency
│   │   ├── hooks/                 # Observation base classes
│   │   ├── observability/         # Langfuse, X-Ray, audit, alerts, cost
│   │   ├── mcp/                   # Base server, cache, provider routing
│   │   ├── gateway/               # AgentCore Gateway client
│   │   ├── memory/                # Three-tier memory manager
│   │   ├── identity/              # OAuth/OIDC providers
│   │   ├── policy/                # Cedar policy builder
│   │   ├── prompt/                # Prompt Registry client
│   │   ├── schemas/               # Config dataclasses
│   │   ├── tools/                 # MCP client factory
│   │   ├── agentcore/             # Multi-tenant + streaming
│   │   └── api/                   # API integrations
│   └── tests/                     # 35+ test modules
├── prompts/                       # prompt-registry
│   ├── src/prompt_registry/       # models, registry, storage, resolver, handler
│   └── tests/
├── artifacts/                     # mcp-artifacts MCP server
│   ├── src/mcp_artifacts/         # server, schemas, storage, catalog, tools/
│   ├── Dockerfile
│   └── tests/
├── cli/                           # agent-cli
│   ├── src/agent_cli/             # main, blueprint, prompt, strategy, graph
│   └── tests/
├── infra/                         # CDK infrastructure
│   ├── app.py                     # CDK app entrypoint
│   ├── config/                    # dev.yaml, staging.yaml, production.yaml
│   ├── stacks/                    # 8 CDK stacks
│   ├── constructs_/               # 7 reusable constructs
│   ├── scripts/                   # build_mcps.sh, package_agents.sh
│   ├── lambda/agents/             # Lambda source templates
│   └── tests/
├── scripts/
│   ├── domain-scan.sh             # Domain contamination scanner
│   └── lock-deps.sh               # Dependency locking
├── .github/workflows/             # 7 CI/CD workflows
├── pyproject.toml                 # Root workspace (test paths, coverage)
├── ruff.toml                      # Linting (py312, 120 chars)
└── sonar-project.properties       # SonarQube multi-module config
```

## License

Private — all rights reserved.
