---
title: generate
nav_order: 7
parent: CLI Reference
---

# agentcli generate

Generate deployment artifacts from an agent blueprint without deploying. Produces the `.bedrock_agentcore.yaml` runtime configuration and a `Dockerfile` that `agentcli deploy` also generates internally.

Use `generate` when you want to inspect or customize artifacts before deployment, or when you manage your own CI/CD pipeline and want to separate artifact generation from the deploy step.

## Synopsis

```
agentcli generate <subcommand> [OPTIONS] YAML_PATH
```

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `runtime-config` | Generate `.bedrock_agentcore.yaml` from an agent blueprint |
| `dockerfile` | Generate a `Dockerfile` from an agent blueprint |

## agentcli generate runtime-config

Generate the `.bedrock_agentcore.yaml` configuration file that the AgentCore starter toolkit reads to configure the runtime.

```
agentcli generate runtime-config YAML_PATH [OPTIONS]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `YAML_PATH` | Path to the agent blueprint YAML file |

### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output-dir` | `-o` | `.` | Directory to write `.bedrock_agentcore.yaml` into |
| `--entrypoint` | `-e` | `app.py` | Python entrypoint file name |

### Example

```bash
# Generate into current directory
agentcli generate runtime-config agents/my-agent.yaml
# Generated: .bedrock_agentcore.yaml

# Generate into a specific directory
agentcli generate runtime-config agents/my-agent.yaml \
  --output-dir build/ \
  --entrypoint handler.py
# Generated: build/.bedrock_agentcore.yaml
```

## agentcli generate dockerfile

Generate a production `Dockerfile` from an agent blueprint.

```
agentcli generate dockerfile YAML_PATH [OPTIONS]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `YAML_PATH` | Path to the agent blueprint YAML file |

### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output-dir` | `-o` | `.` | Directory to write `Dockerfile` into |
| `--base-image` | | `python:3.12-slim` | Docker base image |
| `--requirements` | `-r` | `requirements.txt` | Requirements file to install |

### Examples

```bash
# Generate with defaults
agentcli generate dockerfile agents/my-agent.yaml
# Generated: ./Dockerfile

# Specify a custom base image and requirements file
agentcli generate dockerfile agents/my-agent.yaml \
  --base-image python:3.12-slim \
  --requirements requirements-prod.txt \
  --output-dir build/
# Generated: build/Dockerfile
```

## Generated Dockerfile Format

The generated Dockerfile follows the AgentCore container contract: expose port 8080, run via `agent_core.runtime.entrypoint`.

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "agent_core.runtime.entrypoint"]
```

The `agent_core.runtime.entrypoint` module starts an HTTP server on port 8080 and registers your blueprint's entrypoint handler for the `/invocations` route.

## CI/CD Usage

In a CI/CD pipeline, generate and inspect artifacts before the deploy step:

```bash
# Step 1: Validate the blueprint
agentcli blueprint lint agents/my-agent.yaml

# Step 2: Generate artifacts
agentcli generate runtime-config agents/my-agent.yaml --output-dir dist/
agentcli generate dockerfile agents/my-agent.yaml --output-dir dist/

# Step 3: Inspect or commit the artifacts
cat dist/.bedrock_agentcore.yaml
cat dist/Dockerfile

# Step 4: Build and push the container image separately
docker build -f dist/Dockerfile -t my-agent:$VERSION .
docker push $ECR_REPO/my-agent:$VERSION
```

## Difference from `agentcli deploy`

| | `agentcli generate` | `agentcli deploy` |
|---|---|---|
| Generates `.bedrock_agentcore.yaml` | Yes | Yes |
| Generates `Dockerfile` | Yes | Yes |
| Builds Docker image | No | Yes |
| Pushes to ECR | No | Yes |
| Creates AgentCore Runtime | No | Yes |

Use `generate` for inspection, customization, or custom CI pipelines. Use `deploy` for a one-command full deployment.

## See Also

- [agentcli deploy](deploy) — full deployment workflow
- [Runtime Concepts](../concepts/runtime) — the `/invocations` + `/ping` container contract
- [agentcli blueprint lint](blueprint) — validate the blueprint before generating artifacts
