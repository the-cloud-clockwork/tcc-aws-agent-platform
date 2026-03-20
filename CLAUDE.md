# AWS Agent Platform — Project Instructions

> **This is a generic, domain-agnostic AI agent platform.**
> It is analogous to AWS Bedrock AgentCore — a runtime, not a business application.
> Domain-specific logic (trading agents, MCPs, risk engines, workflows) lives in separate repos that **consume** this platform via published packages.

---

## What This Repo Is

A monorepo providing the foundational runtime, tooling, and infrastructure for AI agent systems built on AWS Strands Agents SDK. It contains 5 independent modules that together form a complete agent platform:

| Module | Package | Purpose |
|--------|---------|---------|
| `core/` | `agent-core` (CodeArtifact) | Blueprint engine, execution modes, runtime handlers, hooks, schemas, observability, MCP base classes, session management, idempotency |
| `prompts/` | `prompt-registry` (CodeArtifact) | Versioned prompt management — S3 storage + DynamoDB metadata + mode-gated resolution |
| `artifacts/` | `mcp-artifacts` (Docker) | Universal artifact store MCP server — S3 + DynamoDB catalog + signed URLs + claim-check pattern |
| `cli/` | `agent-cli` (pip) | CLI for blueprint validation, prompt management, strategy lifecycle, graph rendering |
| `infra/` | `agent-infra` (CDK) | 8 CDK stacks + 7 reusable constructs — VPC, Lambda, ECS Fargate, Step Functions, DynamoDB, S3, KMS, API Gateway, CloudWatch |

### How Domain Repos Consume This Platform

```
Domain repo (e.g., tccw-qitp)
  └── agents/        → imports agent-core from CodeArtifact
  └── mcps/          → imports agent_core.mcp.* for base server, cache, routing
  └── infra/         → reads platform SSM params, deploys domain resources on top
```

The platform deploys FIRST (base infrastructure). Domain repos deploy SECOND (domain resources plugged into platform infrastructure).

---

## The #1 Rule: ZERO Domain Contamination

**`scripts/domain-scan.sh` must return ZERO hits.** No exceptions. No "INFRA-OK" tags.

This repo must never contain:
- Domain-specific package names (`qitp_*`, `tccw_*`)
- Broker references (`ibkr`, `interactive_brokers`)
- Regulatory terms (`cnmv`, `esma`, `mifid`)
- Trading terms (`ohlcv`, `trailing_stop`, `gap_pct`, `watchlist`)
- Domain MCP names (`market-data-mcp`, `sentiment-mcp`, `backtest-mcp`, etc.)
- Domain agent names (`gap-detector`, `sentiment-analyzer`, etc.)

Run the scanner:
```bash
./scripts/domain-scan.sh          # HARD terms only (must be ZERO)
./scripts/domain-scan.sh --full   # HARD + SOFT terms (advisory)
```

---

## Module Details

### `core/` — Agent Core (v0.7.0)

The SDK library that all agents import. 48 public exports organized into subsystems:

| Subsystem | Key Classes | Purpose |
|-----------|-------------|---------|
| `blueprints/` | `AgentBlueprint`, `StrategyBlueprint`, `WorkflowBlueprint`, `BlueprintLoader` | YAML → Pydantic → configured agent |
| `execution/` | `ExecutionMode`, `get_execution_mode()` | `EXECUTION_MODE=simulation\|staging\|production` routing |
| `runtime/` | `GenericHandler`, `AgentConfig`, `SessionManager`, `IdempotencyStore` | Lambda handler, session lifecycle, idempotency |
| `hooks/` | `ObservabilityHook`, `CompositeObservabilityHook` | Pluggable instrumentation |
| `observability/` | `AuditLogWriter`, `LangfuseHook`, `XRayTracer`, `CostTracker`, `AlertPublisher` | Full observability stack |
| `mcp/` | `BaseMCPServer`, `cache_get/set`, `resolve_provider`, `VersionedS3Store` | Shared MCP infrastructure (used by domain MCPs) |
| `gateway/` | `GatewayClient`, `TargetRegistry`, `ToolDiscovery` | AgentCore Gateway integration |
| `memory/` | `MemoryManager`, `SessionBridge` | Three-tier memory (short/long/episodic) |
| `identity/` | `IdentityProvider` | OAuth/OIDC provider abstraction |
| `policy/` | `CedarPolicyBuilder` | Cedar policy generation |
| `prompt/` | `PromptRegistryClient` | HTTP client for prompt versioning |
| `tools/` | `create_mcp_client()` | Dynamic MCP client factory |
| `schemas/` | `ModelConfig`, `ToolConfig`, `RuntimeConfig` | Configuration dataclasses |

### `prompts/` — Prompt Registry (v0.1.0)

HTTP API for versioned prompt management. Enforces the "zero hardcoded prompts" rule.

- **CRUD:** create, get, list versions, promote, rollback, diff
- **Mode-gated:** production only sees STABLE; dev/simulation can use DRAFT
- **Storage:** S3 for content, DynamoDB for metadata

### `artifacts/` — Artifacts MCP Server (v0.1.0)

MCP server implementing the claim-check pattern (Step Functions 256KB limit).

- **4 tools:** `create_artifact`, `get_artifact`, `poll_artifact`, `list_artifacts`
- **6 artifact types:** chart, report, analysis_result, recommendation, image, data_export
- **Idempotency:** duplicate writes prevented via idempotency keys
- **Runs on:** Docker/ECS Fargate (port 8080)

### `cli/` — Agent CLI (v0.1.0)

Developer tooling. Entry point: `agentcli`.

- `agentcli blueprint lint` — Validate agent/strategy YAML
- `agentcli prompt push/get/list/diff/promote/rollback` — Prompt Registry management
- `agentcli strategy validate/list/promote` — Strategy lifecycle
- `agentcli graph render` — Multi-agent topology visualization (ASCII diagrams)

### `infra/` — CDK Infrastructure (v0.2.0)

Configuration-driven CDK stacks. All resource names come from `config/{env}.yaml`.

| Stack | Resources |
|-------|-----------|
| `DataStack` | DynamoDB tables (artifacts, audit_log, prompt_registry, run_history, idempotency) + S3 buckets |
| `NetworkStack` | VPC (3-tier subnets, NAT) + security groups |
| `SecurityStack` | KMS CMKs + Secrets Manager + WAF + VPC endpoints |
| `AgentStack` | Lambda functions + Strands SDK layer + IAM roles |
| `McpStack` | ECS Fargate cluster + Cloud Map namespace + ECR repos |
| `ObservabilityStack` | CloudWatch dashboard + SNS alerts + X-Ray group |
| `ApiStack` | API Gateway + throttling + CORS |
| `WorkflowStack` | Step Functions state machine templates |

**Reusable constructs:** `McpServiceConstruct`, `StrandsAgentTask`, `SfnWorkflow`, `FargateAutoScaling`, `LambdaProvisionedConcurrency`, `WafWebAcl`, `VpcEndpointsConstruct`

**SSM parameter namespace:** `/platform/{env}/tables/*/name`, `/platform/{env}/buckets/*/name`, `/platform/{env}/agents/*/arn`, `/platform/{env}/mcps/*/endpoint`, etc.

---

## AWS Configuration

| Setting | Value |
|---------|-------|
| Account | `835618032093` |
| Primary Region | `eu-west-1` |
| Bedrock Region | `us-west-2` |
| CodeArtifact Domain | `platform` |
| CodeArtifact Repo | `platform-python` |
| SonarQube Project | `aws-agent-platform` (5 modules) |

---

## Development Workflow

### Per-Component Install

```bash
pip install -e "core/[dev]"       # agent-core
pip install -e "prompts/[dev]"    # prompt-registry
pip install -e "artifacts/[dev]"  # mcp-artifacts
pip install -e "cli/[dev]"        # agent-cli (depends on agent-core)
pip install -e "infra/[dev]"      # CDK stacks
```

### CDK Deploy

```bash
cd infra
cdk synth -c env=dev          # Synthesize
cdk deploy -c env=dev         # Deploy all stacks
cdk deploy -c env=dev DataStack AgentStack   # Deploy specific stacks
```

Environments: `dev` (on-demand, minimal), `staging` (provisioned, moderate), `production` (full HA, WAF, scaling).

### Linting

```bash
ruff check .                  # All modules
ruff format --check .         # Format check
```

Config: `ruff.toml` — Python 3.12, line-length 120, isort with known-first-party modules.

---

## CI/CD

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci-core.yml` | `core/**` changes | pytest + ruff + mypy |
| `ci-prompts.yml` | `prompts/**` changes | pytest + ruff |
| `ci-artifacts.yml` | `artifacts/**` changes | pytest + ruff |
| `ci-cli.yml` | `cli/**` changes | pytest + ruff |
| `ci-infra.yml` | `infra/**` changes | pytest + ruff + cdk synth |
| `publish.yml` | `v*` tags | Build + publish to CodeArtifact |
| `sonar-scan.yml` | Push/PR to main | Multi-module SonarQube analysis |

---

## Key Architectural Principles

1. **Zero domain contamination** — `domain-scan.sh` HARD terms must return zero
2. **Configuration-driven** — All resource names from YAML config, not hardcoded
3. **Claim-check pattern** — Large outputs in S3, only keys through Step Functions
4. **Idempotency everywhere** — DynamoDB-backed idempotency keys on all writes
5. **Execution mode routing** — `EXECUTION_MODE` env var drives all behavior
6. **Published packages** — `agent-core` and `prompt-registry` on CodeArtifact for domain consumption
7. **Multi-tenant ready** — Memory branching + tenant isolation in agent-core
8. **Observability first** — Langfuse, X-Ray, CloudWatch, structured logging, audit log

---

## Constraints

- **Never import domain packages** — No `qitp_*`, no domain-specific logic
- **Never hardcode resource names** — Everything from `config/{env}.yaml`
- **Never run tests locally** — CI only (pytest hangs on this machine)
- **Commit directly to main** — Scratch phase, no branches, no PRs
- **CDK Python only** — No Terraform, no CloudFormation YAML
- **Tests are separate sessions** — Never interleave test runs with implementation work

---

## File Structure Reference

```
tccw-aws-agent-platform/
├── core/                    # agent-core SDK (64 source files, 35+ test files)
│   ├── src/agent_core/      # 15 subsystems
│   └── tests/
├── prompts/                 # prompt-registry service
│   ├── src/prompt_registry/
│   └── tests/
├── artifacts/               # mcp-artifacts MCP server
│   ├── src/mcp_artifacts/
│   ├── Dockerfile
│   └── tests/
├── cli/                     # agent-cli developer tooling
│   ├── src/agent_cli/
│   └── tests/
├── infra/                   # CDK infrastructure
│   ├── app.py
│   ├── config/              # dev.yaml, staging.yaml, production.yaml
│   ├── stacks/              # 8 CDK stacks
│   ├── constructs_/         # 7 reusable constructs
│   ├── scripts/             # build_mcps.sh, package_agents.sh
│   └── tests/
├── scripts/
│   ├── domain-scan.sh       # Domain contamination scanner
│   └── lock-deps.sh         # Dependency locking
├── .github/workflows/       # 7 CI/CD workflows
├── pyproject.toml            # Root workspace config
├── ruff.toml                 # Linting config
└── sonar-project.properties  # SonarQube multi-module config
```
