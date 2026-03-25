---
title: deploy
nav_order: 4
parent: CLI Reference
---

# agentcli deploy

Build and deploy agents to Amazon Bedrock AgentCore Runtime. Reads an agent blueprint YAML, generates deployment artifacts (`.bedrock_agentcore.yaml` and `Dockerfile`), then uses the AgentCore starter toolkit to build the container, push it to ECR, and create the Runtime.

## Synopsis

```
agentcli deploy <subcommand> [OPTIONS] YAML_PATH
```

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `agent` | Deploy a single agent blueprint to AgentCore Runtime |

## agentcli deploy agent

```
agentcli deploy agent YAML_PATH [OPTIONS]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `YAML_PATH` | Path to the agent blueprint YAML file |

### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--env` | `-e` | `dev` | Target environment (`dev`, `staging`, `production`) |
| `--region` | `-r` | `$AWS_DEFAULT_REGION` | AWS region. Reads `AWS_DEFAULT_REGION` if not set |
| `--entrypoint` | | `app.py` | Python entrypoint file name |
| `--requirements` | | `requirements.txt` | Python requirements file |
| `--dry-run` | | `false` | Generate artifacts only — do not deploy |

### Requirements

- `bedrock-agentcore-starter-toolkit` must be installed (`pip install bedrock-agentcore-starter-toolkit`)
- AWS credentials must be configured with permissions to create ECR repositories, push images, and create AgentCore Runtimes
- `AWS_DEFAULT_REGION` must be set, or pass `--region`

## Deployment Steps

The deploy command executes a three-step workflow:

1. **Generate `.bedrock_agentcore.yaml`** — runtime configuration derived from the blueprint's `runtime`, `identity`, and `model` blocks
2. **Generate `Dockerfile`** — a production-ready Dockerfile with the correct base image and CMD
3. **Launch via starter toolkit** — builds the Docker image, pushes to ECR (auto-creates the repository if needed), and calls `create_agent_runtime()` on AgentCore

## Examples

### Deploy to dev

```bash
agentcli deploy agent agents/my-agent.yaml
# Uses env=dev and AWS_DEFAULT_REGION
```

### Deploy to production with explicit region

```bash
agentcli deploy agent agents/my-agent.yaml \
  --env production \
  --region ${AWS_REGION}
```

### Dry run — generate artifacts without deploying

Useful for inspecting generated files or running in CI before a real deployment:

```bash
agentcli deploy agent agents/my-agent.yaml --dry-run
# Generated: .bedrock_agentcore.yaml
# Generated: Dockerfile
# Dry run complete. Artifacts generated, no deployment.
```

### Deploy with a custom entrypoint

```bash
agentcli deploy agent agents/my-agent.yaml \
  --entrypoint handler.py \
  --requirements requirements-prod.txt
```

## Generated Artifacts

### `.bedrock_agentcore.yaml`

The AgentCore configuration file consumed by the starter toolkit. Derived from the blueprint's `runtime` block.

### `Dockerfile`

A production Dockerfile. Example output:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "agent_core.runtime.entrypoint"]
```

## Identity / Auth Wiring

If the blueprint declares an `identity.authorizer` block, the CLI automatically configures AgentCore's JWT authorizer:

```yaml
# In your blueprint:
identity:
  authorizer:
    type: cognito_jwt
    user_pool_id: ${COGNITO_USER_POOL_ID}
    client_id: ${COGNITO_CLIENT_ID}
```

The CLI reads the referenced environment variables at deploy time and passes the Cognito discovery URL to the Runtime's authorizer configuration. No manual wiring required.

## Network Mode

To deploy in private VPC mode, set `runtime.network_mode: PRIVATE` in the blueprint:

```yaml
runtime:
  type: agentcore
  network_mode: PRIVATE
```

The CLI passes this through to the starter toolkit's `configure()` call.

## See Also

- [Runtime Concepts](../concepts/runtime) — what AgentCore Runtime is and how it works
- [agentcli generate](generate) — generate artifacts without deploying
- [agentcli blueprint lint](blueprint) — validate the blueprint before deploying
