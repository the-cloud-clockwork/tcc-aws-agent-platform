# AWS Agent Platform — Monorepo

> **Generic, domain-agnostic AI agent platform.**
> This monorepo contains the control plane: Blueprint Engine, Prompt Registry, Artifacts MCP, CLI, and CDK infrastructure.
> Domain-specific code lives in separate domain repos.

## Repository Structure

```
aws-agent-platform/               ← THIS REPO
├── core/                          agent-core library (CodeArtifact: agent-core)
│   ├── src/agent_core/            Blueprint Engine, execution modes, hooks, schemas, gateway, memory, identity, policy
│   └── tests/
├── prompts/                       prompt-registry service (CodeArtifact: prompt-registry)
│   ├── src/prompt_registry/       Versioned prompt management (S3 + DynamoDB)
│   └── tests/
├── artifacts/                     mcp-artifacts server (Docker)
│   ├── src/mcp_artifacts/         S3 artifact store, signed URLs, polling
│   └── tests/
├── cli/                           agent-cli tool (pip: agentcli)
│   ├── src/agent_cli/             Prompt management, strategy validation, graph rendering
│   └── tests/
├── infra/                         CDK stacks (Python)
│   ├── stacks/                    DataStack, NetworkStack, AgentStack, McpStack, ObservabilityStack, SecurityStack
│   ├── constructs/                Reusable CDK constructs
│   ├── lambda/                    Lambda handler code
│   ├── config/                    dev.yaml, staging.yaml, production.yaml
│   └── tests/
├── pyproject.toml                 Root workspace (NOT a package)
├── ruff.toml                      Shared linting config
├── sonar-project.properties       Multi-module SonarQube config
└── .github/workflows/             CI/CD pipelines
```

## Components

| Component | Package | Type | Dependencies |
|-----------|---------|------|-------------|
| `core/` | `agent-core` | Python library (CodeArtifact) | strands-agents, pydantic, pyyaml, httpx |
| `prompts/` | `prompt-registry` | Python library (CodeArtifact) | boto3, pydantic |
| `artifacts/` | `mcp-artifacts` | MCP server (Docker) | mcp[server], boto3, pydantic, uvicorn |
| `cli/` | `agent-cli` | CLI tool (pip) | typer, rich, httpx, pyyaml, agent-core |
| `infra/` | `agent-infra` | CDK stacks | aws-cdk-lib, constructs, pyyaml |

## Domain Isolation — NON-NEGOTIABLE

This repo is a **pure AWS-agnostic agent platform**. It is modeled after [Amazon Bedrock AgentCore samples](https://github.com/aws-samples/amazon-bedrock-agentcore-samples) — it provides infrastructure scaffolding that any agentic workflow can run on top of.

### What this repo IS
- An AWS Cloud Native agent runner — VPC, ECS, Lambda runtime, API Gateway, Step Functions, observability
- A Strands Agents + Bedrock AgentCore integration layer — blueprint engine, gateway, memory, identity, Cedar policies
- Generic platform services — artifacts store, prompt registry, CLI
- CDK stacks for **platform-level** resources only (generic tables, S3 buckets, queues)

### What this repo is NOT
- Not a trading platform. Not a risk engine. Not a CNMV compliance tool.
- Not a place for ANY domain-specific infrastructure (DynamoDB tables, Lambdas, EventBridge rules, SNS topics) that serve a specific business domain.

### Hard Rules
1. **Zero domain imports** — No module may import from `qitp_*` or any domain-specific package
2. **Zero domain terms** — No trading, risk, CNMV, IBKR, sentiment, gap, or any QITP concept in source code, CDK configs, or resource names
3. **Zero domain infrastructure** — CDK config tables must be generic platform tables. If a domain needs a DynamoDB table, Lambda, or EventBridge rule, the domain repo deploys it
4. **Multi-tenant by design** — Another team with a completely different use case (e.g., content moderation, data pipeline) should be able to use this platform with zero trading artifacts in their account
5. **Platform CDK configs** — Only generic resources: `artifacts`, `audit_log`, `prompt_registry`, `run_history`, `idempotency`. Domain-specific tables like `risk_state`, `watchlist`, `2fa_events` belong in the domain repo's own CDK

## Development

### Setup

```bash
# Create venv
python3.12 -m venv .venv && source .venv/bin/activate

# Install a component in editable mode (with dev deps)
pip install -e "core/[dev]"
pip install -e "prompts/[dev]"
pip install -e "artifacts/[dev]"
pip install -e "cli/[dev]"
pip install -e "infra/[dev]"
```

### Running Tests

```bash
# Single component
cd core && pytest
cd prompts && pytest
cd artifacts && pytest
cd cli && pytest
cd infra && pytest

# All components from root
pytest
```

### Linting

```bash
ruff check .
ruff format --check .
```

### CDK

```bash
cd infra
cdk synth -c env=dev
cdk diff -c env=dev
cdk deploy -c env=dev
```

## AWS Configuration

| Setting | Value |
|---------|-------|
| Account | `835618032093` |
| Primary Region | `eu-west-1` |
| Bedrock Region | `us-west-2` |
| CodeArtifact Domain | `platform` |
| CodeArtifact Repo | `platform-python` |
| SonarQube | `sonar.homeofanton.com` |

## CI/CD

| Workflow | Trigger | What it does |
|----------|---------|-------------|
| `ci-core.yml` | Push/PR changing `core/` | Lint + test + coverage for agent-core |
| `ci-prompts.yml` | Push/PR changing `prompts/` | Lint + test + coverage for prompt-registry |
| `ci-artifacts.yml` | Push/PR changing `artifacts/` | Lint + test + coverage for mcp-artifacts |
| `ci-cli.yml` | Push/PR changing `cli/` | Lint + test + coverage for agent-cli |
| `ci-infra.yml` | Push/PR changing `infra/` | Lint + test + CDK synth for agent-infra |
| `publish.yml` | Tag `v*` on main | Publish libraries to CodeArtifact |
| `sonar-scan.yml` | Push to main | SonarQube multi-module scan |

## Naming Conventions

- Python packages: `agent_core`, `prompt_registry`, `mcp_artifacts`, `agent_cli`
- CDK stacks: `DataStack`, `NetworkStack`, `AgentStack`, `McpStack`, `ObservabilityStack`, `SecurityStack`
- No domain-specific prefix anywhere in this repo
