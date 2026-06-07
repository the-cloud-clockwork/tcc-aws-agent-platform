---
title: CLI Reference
nav_order: 12
has_children: true
---

# CLI Reference

`agentcli` is the developer CLI for the AWS Agent Platform. It covers the full agent development lifecycle: blueprint validation, prompt management, graph visualization, deployment, policy generation, evaluation, and artifact generation.

## Installation

The CLI is published as the `agent-cli` package alongside `agent-core`. Install it from your configured package registry:

```bash
pip install agent-cli
```

For development (editable install from the repository source):

```bash
pip install -e "cli/[dev]"
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `AGENT_REGISTRY_URL` | Prompt Registry HTTP API base URL (default: `http://localhost:8000`). Used when the registry is accessed over HTTP. |
| `AWS_DEFAULT_REGION` | AWS region for deployment operations (`agentcli deploy`) |
| `AWS_REGION` | AWS region for evaluation operations (`agentcli eval`) |

## Command Groups

| Command | Description |
|---------|-------------|
| [`agentcli blueprint`](blueprint) | Lint and validate agent, strategy, and workflow blueprint YAML files |
| [`agentcli prompt`](prompt) | Push, get, list, diff, promote, and rollback versioned prompt templates |
| [`agentcli graph`](graph) | Render ASCII topology diagrams from multi-agent graph blueprints |
| [`agentcli deploy`](deploy) | Build and deploy agents to Amazon Bedrock AgentCore Runtime |
| [`agentcli policy`](policy) | Validate and generate Cedar policies from blueprint rules |
| [`agentcli eval`](evaluation) | Run on-demand evaluation and check online evaluation status |
| [`agentcli generate`](generate) | Generate deployment artifacts (runtime config, Dockerfile) from blueprints |

## Quick Reference

```bash
# Validate a blueprint before committing
agentcli blueprint lint agents/my-agent.yaml

# Push a new prompt version
agentcli prompt push prompts/system.jinja2 --id my-agent-system --version 1.2.0

# Deploy an agent to AgentCore Runtime
agentcli deploy agent agents/my-agent.yaml --env production

# Generate Cedar policies from blueprint rules
agentcli policy generate agents/my-agent.yaml \
  --gateway-arn "arn:aws:bedrock-agentcore:${AWS_REGION}:${AWS_ACCOUNT_ID}:gateway/my-gateway"

# Run evaluation on a session
agentcli eval run --agent-id my-agent --session-id sess-123 \
  --evaluators Builtin.Correctness,Builtin.GoalSuccessRate

# Dry-run a deploy to generate artifacts without deploying
agentcli deploy agent agents/my-agent.yaml --dry-run
```

## Getting Help

Every command supports `--help`:

```bash
agentcli --help
agentcli blueprint --help
agentcli blueprint lint --help
agentcli prompt --help
agentcli eval run --help
```
