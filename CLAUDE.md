# AWS Agent Platform — Project Instructions

> **A configuration-driven, domain-agnostic runtime that lets you declare AI agents in YAML and deploy them on AWS — built as an abstraction layer over Strands Agents SDK and Amazon Bedrock AgentCore.**
>
> **Status: ~90% production-ready.** Core SDK complete (POSTMORTEM.md all checked off). Infrastructure hardening in progress.

---

## Boot Sequence

**Read these before every session, in order:**

1. `operator/VISION.md` — Intent, philosophy, what and why (operator-owned, never edit without instruction)
2. `operator/SPECS.md` — Technical contract, design decisions, schemas
3. `operator/BLOCKS.md` — Current work blocks and their status

---

## Operator Documents

| Document | Owner | Purpose |
|----------|-------|---------|
| `operator/VISION.md` | **Operator ONLY** | Intent, philosophy, what and why. AI reads but NEVER edits without explicit instruction |
| `operator/SPECS.md` | Operator + AI (with approval) | Technical contract — all design decisions, schemas, behaviors |
| `operator/BLOCKS.md` | Operator + AI | Major work blocks. Status: `design` → `ready` → `in-progress` → `done` |
| `operator/TODO.md` | Operator + AI | Minor items, pending decisions, scratchpad |
| `operator/STATE.md` | Operator + AI | Project health/rating assessment |
| `operator/BUGS.md` | Operator + AI | Bug tracking (P0–P3) |
| `operator/KNOWN-ISSUES.md` | Operator + AI | Known limitations with workarounds |
| `operator/ENHANCEMENTS.md` | Operator + AI | Feature requests and improvement proposals |
| `operator/MVP.md` | Operator + AI | Release status, backlog, completed blocks, release criteria |

### Supporting Directories

| Directory | Purpose |
|-----------|---------|
| `operator/images/` | Screenshots, diagrams, mockups |
| `operator/drafts/` | WIP documents, research, exploration |
| `operator/incidents/` | Post-mortems (`INC-YYYY-MM-DD-slug.md`) |
| `operator/references/` | External research, deep-dives |

---

## Session Protocol

### Active Work: Infrastructure Hardening (`INFRA.md`)

The platform SDK (`core/`, `prompts/`, `artifacts/`, `cli/`) is complete. Current focus is **Terraform infrastructure enhancement and hardening** tracked in `INFRA.md`.

**Work is organized into 3 blocks executed sequentially. The operator assigns the block and tells you to plan or implement.**

#### INFRA Block 1 — Critical Fixes (must-fix for terraform plan/apply)
- Create `placeholder.zip` for Lambda
- Verify/fix `protocol_configuration` (block vs string) in `agents/runtime.tf`
- Fix Memory `event_expiry_duration` min validation (3 not 1) in `agentcore/variables.tf`
- Verify/fix `credential_provider_configurations` (block vs attribute) in `agents/gateway_targets.tf`
- Verify/fix `tool_schema`/`inline_payload` nesting in `agents/gateway_targets.tf`

#### INFRA Block 2 — High-Priority Enhancements (missing resources + security)
- Add `aws_bedrockagentcore_runtime_endpoint` resource
- Add Gateway `kms_key_arn` for encryption
- Add Gateway `policy_engine_configuration` for Cedar policies
- Add Runtime `lifecycle_configuration` (with ignore_changes workaround for provider bug #45290)
- ECR: switch AES256 to KMS encryption
- Scope agent IAM `bedrock:InvokeModel` to blueprint model ARNs (not `*`)
- Add VPC endpoint for `bedrock-agentcore` service (verify service exists first)
- Add `aws_bedrockagentcore_oauth2_credential_provider` resource

#### INFRA Block 3 — Medium-Priority Hardening (best practices + completeness)
- Verify SFN `bedrock-agentcore:invokeAgentRuntime` integration ARN
- Add DynamoDB GSIs for common query patterns
- Verify memory strategy type values against API
- Document CodeBuild `NO_SOURCE` / sourceLocationOverride workflow
- Add cross-region Bedrock provider alias in `providers.tf`
- Add `NONE` to Gateway `authorizer_type` validation
- Remove duplicate tags in `locals.tf` (already in `default_tags`)
- Add `description` to Memory resource

**Workflow per block:**

1. **Operator says "Block N"** — Read `INFRA.md` for the specific findings
2. **Plan** — Enter plan mode. Read every affected file. Propose changes aligned with the vision. Wait for operator approval
3. **Implement** — Execute the approved plan. Address every item in the block
4. **Verify** — Run `./scripts/domain-scan.sh` to confirm zero domain contamination
5. **Update `INFRA.md`** — Mark completed items
6. **Commit** — Descriptive message referencing the INFRA block

### Legacy: SDK Bug Fixes (`POSTMORTEM.md`)

All 14 blocks in `POSTMORTEM.md` are complete (all checkboxes checked). If new SDK issues arise, follow the original protocol:

1. Read `POSTMORTEM.md` for the assigned block
2. Read affected files before modifying
3. Fix every checkbox
4. Run `domain-scan.sh`
5. Update `POSTMORTEM.md` and commit

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

### SDK (Complete — all POSTMORTEM blocks done)

| Block | Subsystem | Key Classes | Status |
|-------|-----------|-------------|--------|
| 1 | `runtime/` | `AgentCoreApp`, `GenericHandler`, `SessionManager` | Done |
| 2 | `gateway/` | `GatewayClient`, `TargetRegistry`, `ToolDiscovery` | Done |
| 3 | `identity/` | `IdentityProvider`, `IdentityClient`, `CredentialCache` | Done |
| 4 | `memory/` | `MemoryManager`, `MemoryHookProvider`, `MemoryBranchManager` | Done |
| 5 | `tools/` | `CodeInterpreterProvider`, `BrowserProvider`, `BuiltinToolWiring` | Done |
| 6 | `observability/` | `LangfuseHook`, `AuditLogWriter`, `XRayTracer`, `CostTracker` | Done |
| 7 | `evaluation/` | `EvaluationClient`, `BuiltinEvaluators` (13) | Done |
| 8 | `policy/` | `PolicyClient`, `CedarPolicyBuilder`, `PolicyTranslator` | Done |
| 9 | `blueprints/` | `BlueprintLoader`, `AgentSession`, `AgentBlueprint` | Done |
| 10 | `a2a/` | `A2AServerWrapper`, `A2AClient`, `A2AWiring` | Done |
| 12 | `schemas/` | `AgentBlueprint`, `StrategyBlueprint`, `WorkflowBlueprint` | Done |

### Infrastructure (In progress — see `INFRA.md`)

| Module | Sub-Modules | Resources | Status |
|--------|-------------|-----------|--------|
| `modules/platform/` | 6 sub-modules (network, security, data, observability, api, agentcore) | ~119 | Wiring complete, hardening in progress |
| `modules/agents/` | Single module, blueprint-driven `for_each` | 30+ per agent | Provider schema verification needed |
| `modules/workflows/` | Single module, workflow-driven `for_each` | 10+ per workflow | SFN integration verification needed |

**`INFRA.md` tracks infrastructure hardening with 22 findings across 3 blocks.**

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

### Universal

1. **Zero domain contamination** — `domain-scan.sh` must return zero
2. **No hardcoded defaults** — No model names, regions, temperatures, sampling rates. Everything from blueprints/env/config
3. **No backward compatibility** — Build for the vision. No fallbacks, no dual paths, no `try/except ImportError`
4. **Hard dependencies** — `bedrock_agentcore` and `strands` are required. If missing, fail loudly
5. **Configuration-driven** — All resource names from config, not hardcoded
6. **Claim-check pattern** — Large outputs in S3, only keys through Step Functions
7. **IaC: Terraform only** — `modules/` is the sole infrastructure source
8. **Never run tests locally** — CI only
9. **Commit directly to main** — No branches, no PRs

### Infrastructure-Specific (Terraform)

10. **Envelope encryption** — 5 KMS keys (data, storage, secrets, platform_artifacts, domain_artifacts). Every data store must use the correct key. Never AES256 when KMS is available
11. **Conditional resources** — WAF, CloudFront, Cognito, builtin tools are all gated by variables. Never create resources unconditionally when a toggle exists
12. **Sub-module interfaces are locked** — The root `platform/main.tf` and sub-module `variables.tf`/`outputs.tf` interfaces are production-grade and verified. Do not change variable names or output names without updating all consumers
13. **Provider schema verification** — `aws_bedrockagentcore_*` resources are new (provider >= 6.21). When adding or modifying AgentCore resources, cross-reference against the [CloudFormation schema](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/AWS_BedrockAgentCore.html) and run `terraform validate`
14. **Blueprint-driven scaling** — `agents/` and `workflows/` modules use `for_each` over YAML blueprints. Never hardcode agent counts, workflow definitions, or resource names in Terraform
15. **Least privilege IAM** — Scope permissions to specific ARNs where possible. Wildcards only where the API requires them (ecr:GetAuthorizationToken, xray:Put*)
16. **Three tfvars environments** — `dev.tfvars`, `staging.tfvars`, `production.tfvars` exist and define environment-specific values. New variables must have sensible defaults or be added to all three
17. **Cross-reference INFRA.md** — Before modifying any Terraform file, check `INFRA.md` for known issues and context on that resource

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
├── operator/                # Operator-driven development docs
│   ├── VISION.md            # Intent & philosophy (operator-owned)
│   ├── SPECS.md             # Technical contract
│   ├── BLOCKS.md            # Work blocks & status
│   ├── TODO.md              # Minor items & scratchpad
│   ├── STATE.md             # Project health assessment
│   ├── BUGS.md              # Bug tracking (P0–P3)
│   ├── KNOWN-ISSUES.md      # Known limitations
│   ├── ENHANCEMENTS.md      # Feature requests
│   ├── MVP.md               # Release status & criteria
│   ├── images/              # Screenshots, diagrams
│   ├── drafts/              # WIP documents
│   ├── incidents/           # Post-mortems
│   └── references/          # External research
├── .github/workflows/
├── POSTMORTEM.md            # SDK audit — all blocks complete
├── INFRA.md                 # Infrastructure hardening — 3 blocks, 22 findings
├── pyproject.toml
├── ruff.toml
└── sonar-project.properties
```
