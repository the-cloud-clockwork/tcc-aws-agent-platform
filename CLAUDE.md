# AWS Agent Platform — Project Instructions

> **This is a generic, domain-agnostic AI agent platform.**
> It is analogous to AWS Bedrock AgentCore — a runtime, not a business application.
> Domain-specific logic (trading agents, MCPs, risk engines, workflows) lives in separate repos that **consume** this platform via published packages.

---

## Session Protocol

**Every task follows this exact sequence:**

### Before writing code

1. **Receive task** — The user submits a block or checkbox from `PROGRESS.md`
2. **Analyze** — Understand what the task requires, which blocks it touches
3. **Read `VISION.md`** — The 12 building blocks and what the platform is becoming
4. **Read `resources/CONCEPTS.md`** — AgentCore concepts that our blocks must align to
5. **Read `resources/TECHNICAL-GUIDE.md`** (relevant sections) — Deep technical patterns for the blocks this task touches
6. **Read `PROGRESS.md`** — Current status: checked = done, unchecked = needed
7. **Think and plan** — Map the task to blocks, identify what exists vs what's missing, propose the approach
8. **Check reference implementation** — `/home/iamroot/dev/tccw-qitp/agents/` shows how a domain repo consumes this platform (YAML blueprints in `blueprints/agents/*.yaml`, prompt builders in `agent_configs.py`, MCP registry in `mcp_registry.py`, 5-line handler in `app.py`). When designing platform features, check how this consumer would use them.

### After completing work

9. **Update `PROGRESS.md`** — Check off any boxes completed during the session
10. **Vision alignment check** — Ask yourself: does the delivered work align with `VISION.md`? If not, fix it before committing.

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
| Account | `123456789012` |
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
2. **Zero backward compatibility** — See dedicated section below
3. **Configuration-driven** — All resource names from YAML config, not hardcoded
4. **Claim-check pattern** — Large outputs in S3, only keys through Step Functions
5. **Idempotency everywhere** — DynamoDB-backed idempotency keys on all writes
6. **Execution mode routing** — `EXECUTION_MODE` env var drives all behavior
7. **Published packages** — `agent-core` and `prompt-registry` on CodeArtifact for domain consumption
8. **Multi-tenant ready** — Memory branching + tenant isolation in agent-core
9. **Observability first** — Langfuse, X-Ray, CloudWatch, structured logging, audit log

---

## Zero Backward Compatibility

**Nothing is in production. This is development phase. Build for the vision, not for the past.**

The reference implementation (`/home/iamroot/dev/tccw-qitp/agents/`) shows where the consumer model is heading — it already uses YAML blueprints, prompt builders, and MCP registries. But its current patterns (Lambda hosting, direct MCP connections, `mcp_factory`) are the **old** way. The platform must implement the **new** way as defined in VISION.md and CONCEPTS.md. The consumer repos will catch up.

**Rules:**
- **No `enabled` toggles** — Don't add `gateway.enabled`, `memory.enabled`, or any feature flag that preserves an old code path alongside the new one. Implement the vision path. Delete the old path.
- **No fallback implementations** — `bedrock_agentcore` and `strands` are hard dependencies. No `try/except ImportError` with standalone alternatives. If the SDK is missing, fail loudly.
- **No dual code paths** — When replacing a pattern (e.g., direct MCP → Gateway, Lambda hosting → AgentCore Runtime), remove the old path entirely. Don't keep it as a "just in case."
- **No compatibility shims** — Don't wrap old interfaces to make them work with new code. Rewrite the consumer contract cleanly.
- **Replace, don't extend** — When a module is rewritten (e.g., `GatewayClient` from httpx to MCPClient), replace the entire file. Don't layer the new pattern on top of the old one.

**Why:** Every backward-compat toggle, fallback, or dual path doubles the code, doubles the bugs, and slows down reaching the vision. The consumer repos (`tccw-qitp/agents/`) will be updated to match when the platform stabilizes. Build the target state now.

---

## Constraints

- **Never import domain packages** — No `qitp_*`, no domain-specific logic
- **Never hardcode resource names** — Everything from `config/{env}.yaml`
- **Never run tests locally** — CI only (pytest hangs on this machine)
- **Commit directly to main** — Scratch phase, no branches, no PRs
- **IaC: CDK (current) → Terraform (target)** — CDK stacks exist; Terraform modules are the migration target per VISION.md Block 11
- **Tests are separate sessions** — Never interleave test runs with implementation work
- **Always follow the Session Startup Protocol** — Read VISION → CONCEPTS → TECHNICAL-GUIDE → PROGRESS before any task

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
