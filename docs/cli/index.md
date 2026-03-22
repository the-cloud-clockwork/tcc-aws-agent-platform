---
title: CLI Reference
nav_order: 5
has_children: true
parent: Documentation
---

# CLI Reference

`agentcli` is the developer CLI for the AWS Agent Platform. It covers the full agent development lifecycle: blueprint validation, prompt management, graph visualization, deployment, policy generation, evaluation, and artifact generation.

## Installation

```bash
pip install agent-cli
```

For development (editable install from source):

```bash
pip install -e "cli/[dev]"
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `AGENT_REGISTRY_URL` | Prompt Registry API base URL (default: `http://localhost:8000`) |
| `AWS_DEFAULT_REGION` | AWS region for deployment operations |
| `AWS_REGION` | AWS region for evaluation operations |

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
agentcli policy generate agents/my-agent.yaml --gateway-arn arn:aws:...

# Run evaluation on a session
agentcli eval run --agent-id my-agent --session-id sess-123 \
  --evaluators Builtin.Correctness,Builtin.GoalSuccessRate
```

## Getting Help

Every command supports `--help`:

```bash
agentcli --help
agentcli blueprint --help
agentcli blueprint lint --help
```
