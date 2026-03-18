# AWS Agent Platform

Generic, domain-agnostic AI agent platform built on AWS Strands Agents SDK, Bedrock AgentCore, and CDK.

## Components

| Component | Path | Package | Description |
|-----------|------|---------|-------------|
| **Agent Core** | `core/` | `agent-core` | Blueprint Engine, execution modes, hooks, schemas, gateway, memory, identity, policy |
| **Prompt Registry** | `prompts/` | `prompt-registry` | Versioned prompt management with S3 storage and DynamoDB metadata |
| **Artifacts MCP** | `artifacts/` | `mcp-artifacts` | Universal artifact store — S3 backend with signed URLs and polling |
| **Agent CLI** | `cli/` | `agent-cli` | CLI for prompt management, strategy validation, and agent graph rendering |
| **Infrastructure** | `infra/` | `agent-infra` | CDK stacks: Data, Network, Agent, MCP, Observability, Security |

## Quick Start

```bash
# Prerequisites: Python 3.12+, Node.js 20+ (for CDK)
python3.12 -m venv .venv
source .venv/bin/activate

# Install a component
pip install -e "core/[dev]"

# Run tests
cd core && pytest -v

# Lint
ruff check .
```

## Architecture

This platform provides the runtime and tooling layer for AI agent systems. Domain-specific logic (agents, MCP servers, workflows) lives in separate repositories that depend on packages published from this monorepo.

```
┌─────────────────────────────────────────────┐
│           Domain Repos                      │
│  agents / MCPs / risk engine / workflows    │
├─────────────────────────────────────────────┤
│          aws-agent-platform                 │
│  ┌──────────┐ ┌──────────┐ ┌─────────────┐ │
│  │ core     │ │ prompts  │ │ artifacts   │ │
│  │ (lib)    │ │ (lib)    │ │ (MCP)       │ │
│  └──────────┘ └──────────┘ └─────────────┘ │
│  ┌──────────┐ ┌──────────────────────────┐  │
│  │ cli      │ │ infra (CDK stacks)       │  │
│  │ (tool)   │ │ Data|Net|Agent|MCP|Obs   │  │
│  └──────────┘ └──────────────────────────┘  │
├─────────────────────────────────────────────┤
│               AWS Services                   │
│  Lambda | ECS Fargate | Step Functions       │
│  DynamoDB | S3 | Bedrock | CodeArtifact      │
└─────────────────────────────────────────────┘
```

## Development

### Per-Component Install

Each component is an independent Python package with its own `pyproject.toml`:

```bash
pip install -e "core/[dev]"       # agent-core + dev deps
pip install -e "prompts/[dev]"    # prompt-registry + dev deps
pip install -e "artifacts/[dev]"  # mcp-artifacts + dev deps
pip install -e "cli/[dev]"       # agent-cli + dev deps (requires agent-core)
pip install -e "infra/[dev]"     # CDK stacks + dev deps
```

### Testing

```bash
# Single component
cd core && pytest -v

# All components from root
pytest
```

### CDK Deployment

```bash
cd infra
cdk synth -c env=dev
cdk deploy -c env=dev
```

Environments: `dev`, `staging`, `production` (config in `infra/config/`).

## CI/CD

- **Per-component CI** — Each component has its own workflow triggered by path changes
- **SonarQube** — Multi-module scan on push to main
- **Publish** — Libraries pushed to AWS CodeArtifact on version tags (`v*`)

## License

Private
