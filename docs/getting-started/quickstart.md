---
title: Quickstart
nav_order: 1
parent: Getting Started
grand_parent: Documentation
---

# Quickstart

Get a validated agent blueprint running in under 10 minutes.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | Required for all SDK packages |
| AWS CLI | 2.x | Must be configured with credentials (`aws configure`) |
| Terraform | 1.9+ | Required for infrastructure deployment |
| Docker | 24+ | Required for building Runtime container images |
| AWS account | — | Bedrock must be enabled in `${AWS_REGION}` |

---

## Step 1: Install the SDK

```bash
pip install agent-core
```

This installs the core runtime engine, blueprint loader, gateway client, memory manager, identity client, and all supporting subsystems.

---

## Step 3: Install the CLI

```bash
pip install agent-cli
```

This installs the `agentcli` command, which provides blueprint validation, deployment commands, and prompt management.

Verify both installs:

```bash
python -c "import agent_core; print(agent_core.__version__)"
agentcli --version
```

---

## Step 4: Create a Minimal Agent Blueprint

Create the directory structure your domain repo needs:

```bash
mkdir -p blueprints/agents
```

Create `blueprints/agents/my-agent.yaml`:

```yaml
agent_id: my-agent
version: "1.0.0"
description: "A general-purpose assistant agent"

runtime:
  type: agentcore
  max_iterations: 10
  idle_timeout_minutes: 15
  network_mode: PRIVATE
  protocol: HTTP

model:
  provider: bedrock
  model_id: ${MODEL_ID}
  region: ${BEDROCK_REGION}

tools:
  - mcp: my-tools-mcp
    tools: [get_data, create_item]

memory:
  mode: MANAGED
  strategies:
    - type: SEMANTIC
      name: FactExtractor
      namespace: "user/{actorId}/facts/"
  event_expiry_days: 30
  short_term_k: 5

identity:
  authorizer:
    type: cognito_jwt
    user_pool_id: ${COGNITO_POOL_ID}
    client_id: ${COGNITO_CLIENT_ID}

observability:
  enabled: true
  trace_attributes:
    environment: production
    agent.version: "1.0.0"

evaluation:
  online:
    sampling_rate: 100
    evaluators:
      - Builtin.GoalSuccessRate
      - Builtin.Correctness
```

---

## Step 5: Validate the Blueprint

```bash
agentcli blueprint lint blueprints/
```

A valid blueprint produces output like:

```
Validating blueprints/agents/my-agent.yaml ... OK
  runtime: agentcore
  model: ${MODEL_ID}
  tools: 1 MCP target(s)
  memory: MANAGED, 1 strategy
  identity: cognito_jwt
  evaluation: online @ 100%

All blueprints valid.
```

---

## Step 6: What Comes Next

Blueprint validation confirms your YAML is structurally correct. To run the agent, you need:

1. **Infrastructure** — Deploy the platform Terraform modules to provision Gateway, Memory, Runtime, Identity, and Observability. See [Infrastructure]({{ '/docs/infrastructure/' | relative_url }}).
2. **Domain logic** — Write a prompt builder and a 5-line handler. See [First Agent]({{ '/docs/getting-started/first-agent' | relative_url }}).
3. **Deployment** — `agentcli deploy --env production` builds the container, pushes to ECR, and registers the Runtime.

The platform handles steps 1 and 3 end-to-end from the blueprint. You own step 2.

---

## Next Steps

- [Installation]({{ '/docs/getting-started/installation' | relative_url }}) — full package reference and environment variable setup
- [First Agent]({{ '/docs/getting-started/first-agent' | relative_url }}) — complete step-by-step tutorial
- [Agent Blueprint Spec]({{ '/docs/blueprints/agent-blueprint' | relative_url }}) — every field documented
