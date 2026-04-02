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

Supporting dirs: `operator/images/`, `operator/drafts/`, `operator/incidents/`, `operator/references/`

---

## What This Repo Is

A monorepo: four Python modules + Terraform infrastructure for AI agent systems on AWS.

| Module | Package | Purpose |
|--------|---------|---------|
| `core/` | `agent-core` (CodeArtifact) | Blueprint engine, runtime, hooks, schemas, observability, gateway, memory, identity, policy, evaluation, A2A, MCP base classes |
| `prompts/` | `prompt-registry` (CodeArtifact) | Versioned prompt management — S3 + DynamoDB + mode-gated resolution |
| `artifacts/` | `mcp-artifacts` (Docker) | Artifact store MCP server — S3 + DynamoDB + signed URLs + claim-check pattern |
| `cli/` | `agent-cli` (pip) | CLI for blueprint validation, prompt management, strategy lifecycle |
| `modules/` | Terraform IaC | 3 Terraform modules (platform, agents, workflows) — all `aws_bedrockagentcore_*` resources |

Platform deploys FIRST. Domain repos deploy SECOND via `source = "git::repo.git//modules/platform"`.

---

## The #1 Rule: ZERO Domain Contamination

**`scripts/domain-scan.sh` must return ZERO hits.** No domain-specific terms (trading, broker, regulatory, etc.).

---

## Architecture

### SDK (Complete — all POSTMORTEM blocks done)

11 subsystems: runtime, gateway, identity, memory, tools, observability, evaluation, policy, blueprints, a2a, schemas. All done.

### Infrastructure

| Module | Sub-Modules | Status |
|--------|-------------|--------|
| `modules/platform/` | 6 sub-modules (security, data, observability, api, agentcore, prompt_registry). **Networking is externally managed** — VPC, subnets, and security groups are passed in as input variables | Wiring complete, hardening in progress |
| `modules/agents/` | Blueprint-driven `for_each` | Provider schema verification needed |
| `modules/workflows/` | Workflow-driven `for_each` | SFN integration verification needed |

### Network Requirements (for consuming projects)

VPC and subnets are externally managed. Security groups (Agent SG, MCP SG) are **created by this module**.

| Variable | Required | Description |
|----------|----------|-------------|
| `vpc_id` | Yes | VPC ID where platform resources deploy |
| `private_subnet_ids` | Yes | Subnets with NAT egress — used for VPC endpoints and agent runtimes |
| `public_subnet_ids` | No | Public subnets (passed through as output) |
| `isolated_subnet_ids` | No | No-internet subnets (passed through as output) |

**Created by this module (outputs):** `agent_security_group_id` (all outbound, TCP 9000 A2A), `mcp_security_group_id` (TCP 8080 from agents)

---

## AWS Configuration

| Setting | Value |
|---------|-------|
| Account | `835618032093` |
| Primary Region | `eu-west-1` |
| Bedrock Region | `us-west-2` |
| CodeArtifact Domain | `platform` |
| CodeArtifact Repo | `platform-python` |

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

Linting: `ruff check .` and `ruff format --check .`

---

## Key Rules

### Universal

1. **Zero domain contamination** — `domain-scan.sh` must return zero
2. **No hardcoded defaults** — No model names, regions, temperatures, sampling rates. Everything from blueprints/env/config
3. **No backward compatibility** — Build for the vision. No fallbacks, no dual paths
4. **Hard dependencies** — `bedrock_agentcore` and `strands` are required. If missing, fail loudly
5. **Configuration-driven** — All resource names from config, not hardcoded
6. **Claim-check pattern** — Large outputs in S3, only keys through Step Functions
7. **IaC: Terraform only** — `modules/` is the sole infrastructure source
8. **Never run tests locally** — CI only
9. **Commit directly to main** — No branches, no PRs

### Infrastructure-Specific (Terraform)

10. **Networking is external** — This module consumes VPC/subnets/SGs via input variables + `data` sources. Never create VPC, subnet, NAT, IGW, or route table resources
11. **Envelope encryption** — 5 KMS keys. Every data store must use the correct key. Never AES256 when KMS is available
12. **Conditional resources** — WAF, CloudFront, Cognito, builtin tools are all gated by variables
13. **Sub-module interfaces are locked** — Do not change variable/output names without updating all consumers
14. **Provider schema verification** — `aws_bedrockagentcore_*` resources are new (provider >= 6.21). Cross-reference CloudFormation schema
15. **Blueprint-driven scaling** — `agents/` and `workflows/` use `for_each` over YAML blueprints
16. **Least privilege IAM** — Scope permissions to specific ARNs where possible
17. **Three tfvars environments** — `dev.tfvars`, `staging.tfvars`, `production.tfvars`. New variables must be added to all three
