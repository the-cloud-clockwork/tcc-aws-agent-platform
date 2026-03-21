# AWS Agent Platform — Project Instructions

> **A configuration-driven, domain-agnostic runtime that lets you declare AI agents in YAML and deploy them on AWS — built as an abstraction layer over Strands Agents SDK and Amazon Bedrock AgentCore.**

---

## Session Protocol

**Every task follows this sequence:**

1. **Receive task** — The user assigns a block from `POSTMORTEM.md`
2. **Read `POSTMORTEM.md`** — Understand the specific issues, files, and line numbers for the assigned block
3. **Read the affected files** — Understand existing code before modifying
4. **Fix** — Address every checkbox in the assigned block
5. **Verify** — Run `./scripts/domain-scan.sh` to confirm zero domain contamination
6. **Update `POSTMORTEM.md`** — Check off completed items
7. **Commit** — Descriptive message referencing the block

---

## What This Repo Is

A monorepo providing the foundational runtime, tooling, and infrastructure for AI agent systems on AWS. Four Python modules + Terraform infrastructure:

| Module | Package | Purpose |
|--------|---------|---------|
| `core/` | `agent-core` (CodeArtifact) | Blueprint engine, runtime, hooks, schemas, observability, gateway, memory, identity, policy, evaluation, A2A, MCP base classes |
| `prompts/` | `prompt-registry` (CodeArtifact) | Versioned prompt management — S3 + DynamoDB + mode-gated resolution |
| `artifacts/` | `mcp-artifacts` (Docker) | Artifact store MCP server — S3 + DynamoDB + signed URLs + claim-check pattern |
| `cli/` | `agent-cli` (pip) | CLI for blueprint validation, prompt management, strategy lifecycle |
| `modules/` | Terraform IaC | 3 Terraform modules (platform, agents, workflows) — all `aws_bedrockagentcore_*` resources |

### How Domain Repos Consume This Platform

```
Domain repo
  └── agents/        → imports agent-core from CodeArtifact
  └── mcps/          → imports agent_core.mcp.* for base server, cache, routing
  └── infra/         → consumes modules/ via source = "git::repo.git//modules/platform"
```

Platform deploys FIRST. Domain repos deploy SECOND.

---

## The #1 Rule: ZERO Domain Contamination

**`scripts/domain-scan.sh` must return ZERO hits.**

This repo must never contain domain-specific terms (trading, broker, regulatory, etc.).

```bash
./scripts/domain-scan.sh          # HARD terms only (must be ZERO)
./scripts/domain-scan.sh --full   # HARD + SOFT terms (advisory)
```

---

## Core Architecture (12 Building Blocks)

| Block | Subsystem | Key Classes | Status |
|-------|-----------|-------------|--------|
| 1 | `runtime/` | `AgentCoreApp`, `GenericHandler`, `SessionManager` | 75% |
| 2 | `gateway/` | `GatewayClient`, `TargetRegistry`, `ToolDiscovery` | 90% |
| 3 | `identity/` | `IdentityProvider`, `IdentityClient`, `CredentialCache` | 88% |
| 4 | `memory/` | `MemoryManager`, `MemoryHookProvider`, `MemoryBranchManager` | 80% |
| 5 | `tools/` | `CodeInterpreterProvider`, `BrowserProvider`, `BuiltinToolWiring` | 90% |
| 6 | `observability/` | `LangfuseHook`, `AuditLogWriter`, `XRayTracer`, `CostTracker` | 93% |
| 7 | `evaluation/` | `EvaluationClient`, `BuiltinEvaluators` (13) | 85% |
| 8 | `policy/` | `PolicyClient`, `CedarPolicyBuilder`, `PolicyTranslator` | 88% |
| 9 | `blueprints/` | `BlueprintLoader`, `AgentSession`, `AgentBlueprint` | 95% |
| 10 | `a2a/` | `A2AServerWrapper`, `A2AClient`, `A2AWiring` | 93% |
| 11 | `modules/` | Terraform: platform, agents, workflows | 100% |
| 12 | `blueprints/` | `AgentBlueprint`, `StrategyBlueprint`, `WorkflowBlueprint` | 98% |

**`POSTMORTEM.md` tracks all remaining issues with checkboxes per block.**

---

## AWS Configuration

| Setting | Value |
|---------|-------|
| Account | `123456789012` |
| Primary Region | `eu-west-1` |
| Bedrock Region | `us-west-2` |
| CodeArtifact Domain | `platform` |
| CodeArtifact Repo | `platform-python` |
| SonarQube Project | `aws-agent-platform` (4 modules) |

---

## Development Workflow

```bash
pip install -e "core/[dev]"       # agent-core
pip install -e "prompts/[dev]"    # prompt-registry
pip install -e "artifacts/[dev]"  # mcp-artifacts
pip install -e "cli/[dev]"        # agent-cli

cd modules/platform
terraform init && terraform plan -var-file=envs/dev.tfvars
```

### Linting

```bash
ruff check .
ruff format --check .
```

---

## CI/CD

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci-core.yml` | `core/**` changes | pytest + ruff + mypy |
| `ci-prompts.yml` | `prompts/**` changes | pytest + ruff |
| `ci-artifacts.yml` | `artifacts/**` changes | pytest + ruff |
| `ci-cli.yml` | `cli/**` changes | pytest + ruff |
| `publish.yml` | `v*` tags | Build + publish to CodeArtifact |
| `sonar-scan.yml` | Push/PR to main | Multi-module SonarQube analysis |

---

## Key Rules

1. **Zero domain contamination** — `domain-scan.sh` must return zero
2. **No hardcoded defaults** — No model names, regions, temperatures, sampling rates. Everything from blueprints/env/config
3. **No backward compatibility** — Build for the vision. No fallbacks, no dual paths, no `try/except ImportError`
4. **Hard dependencies** — `bedrock_agentcore` and `strands` are required. If missing, fail loudly
5. **Configuration-driven** — All resource names from config, not hardcoded
6. **Claim-check pattern** — Large outputs in S3, only keys through Step Functions
7. **IaC: Terraform only** — `modules/` is the sole infrastructure source
8. **Never run tests locally** — CI only
9. **Commit directly to main** — No branches, no PRs

---

## File Structure

```
tccw-aws-agent-platform/
├── core/                    # agent-core SDK
│   ├── src/agent_core/      # 15 subsystems
│   └── tests/
├── prompts/                 # prompt-registry service
├── artifacts/               # mcp-artifacts MCP server
├── cli/                     # agent-cli tooling
├── modules/                 # Terraform infrastructure
│   ├── platform/            # Core infra (6 sub-modules)
│   ├── agents/              # Per-agent deployment
│   └── workflows/           # Step Functions from YAML
├── scripts/
│   ├── domain-scan.sh
│   └── lock-deps.sh
├── .github/workflows/
├── POSTMORTEM.md            # Remaining work — checkboxes per block
├── pyproject.toml
├── ruff.toml
└── sonar-project.properties
```
