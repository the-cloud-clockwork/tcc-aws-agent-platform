---
title: Quickstart
nav_order: 1
parent: Getting Started
---

# Quickstart

Install the SDK and CLI, write a minimal agent blueprint, and validate it — in under 10 minutes. No AWS infrastructure required for this step.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | 3.12 recommended |
| AWS CLI | 2.x | Must be configured (`aws configure`) |
| Terraform | 1.9+ | Required for infrastructure deployment (not this step) |
| Docker | 24+ | Required for building Runtime images (not this step) |
| AWS account | — | Bedrock must be enabled if you use the `bedrock` provider |

---

## Step 1: Configure Your Package Index

> **Package availability:** `agent-core`, `agent-cli`, `prompt-registry`, and `mcp-artifacts` are currently published to a **private** package registry (AWS CodeArtifact). A public distribution channel (PyPI or GitHub Packages) is planned but not yet available. Until then, access requires an authorized CodeArtifact token from your organization.

Configure pip to point at your organization's registry before installing:

```bash
# Example: AWS CodeArtifact
export CODEARTIFACT_DOMAIN=<your-domain>
export CODEARTIFACT_REPO=<your-repo>
export CODEARTIFACT_ACCOUNT=<your-account-id>
export CODEARTIFACT_REGION=<your-region>

export CODEARTIFACT_AUTH_TOKEN=$(aws codeartifact get-authorization-token \
  --domain "$CODEARTIFACT_DOMAIN" \
  --domain-owner "$CODEARTIFACT_ACCOUNT" \
  --query authorizationToken \
  --output text)

pip config set global.index-url \
  "https://aws:${CODEARTIFACT_AUTH_TOKEN}@${CODEARTIFACT_DOMAIN}-${CODEARTIFACT_ACCOUNT}.d.codeartifact.${CODEARTIFACT_REGION}.amazonaws.com/pypi/${CODEARTIFACT_REPO}/simple/"
```

Replace the placeholder values above with your organization's CodeArtifact domain, repository, account ID, and region.

---

## Step 2: Install the SDK

```bash
pip install agent-core
```

This installs the core runtime engine: BlueprintLoader, GenericHandler, Gateway client, Memory manager, Identity client, Policy engine, Observability hooks, Evaluation wiring, A2A server/client, and MCP base classes.

To install provider-specific extras:

```bash
pip install "agent-core[litellm]"     # LiteLLM proxy support
pip install "agent-core[anthropic]"   # Direct Anthropic API
pip install "agent-core[presidio]"    # Local PII filtering (Microsoft Presidio)
```

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

## Step 4: Create a Minimal Blueprint

Create the directory structure:

```bash
mkdir -p blueprints/agents
```

Create `blueprints/agents/my-agent.yaml`. Choose the provider that matches your setup:

### Option A — Amazon Bedrock (default)

```yaml
id: my-agent
name: My Agent
version: "1.0.0"
description: "A general-purpose assistant agent"

prompt_ref: my-agent-system-v1

model:
  provider: bedrock                         # default; requires BEDROCK_REGION env var
  model_id: ${MODEL_ID}                     # supports ${VAR:-default} expansion
  temperature: 0.3
  max_tokens: 4096

runtime:
  type: agentcore
  max_iterations: 10
  idle_timeout_minutes: 15
  network_mode: PRIVATE
  protocol: HTTP

gateway:
  auth_type: aws_iam

observability:
  enabled: true
  trace_attributes:
    environment: development
```

### Option B — LiteLLM Proxy (OpenAI-compatible endpoint)

```yaml
id: my-agent
name: My Agent
version: "1.0.0"
description: "A general-purpose assistant agent"

prompt_ref: my-agent-system-v1

model:
  provider: litellm
  model_id: claude-sonnet-4-6              # model name the proxy expects
  temperature: 0.3
  max_tokens: 4096
  base_url: ${LITELLM_BASE_URL}            # e.g. https://llm.example.com
  api_key_env: LITELLM_API_KEY             # env var name holding the key
  # optional: pass extra headers (e.g. for Cloudflare Access)
  # extra_headers_env:
  #   CF-Access-Client-Id: CF_ACCESS_CLIENT_ID
  #   CF-Access-Client-Secret: CF_ACCESS_CLIENT_SECRET

runtime:
  type: agentcore
  max_iterations: 10
  idle_timeout_minutes: 15
  network_mode: PRIVATE
  protocol: HTTP

gateway:
  auth_type: aws_iam

observability:
  enabled: true
  trace_attributes:
    environment: development
```

{: .note }
> `model_id`, `temperature`, and `max_tokens` are required with no defaults — the platform never assumes a model or sampling parameters. `provider` defaults to `bedrock`.

---

## Step 5: Validate the Blueprint

```bash
agentcli blueprint lint blueprints/agents/my-agent.yaml
```

A valid blueprint produces output like:

```
Validating blueprints/agents/my-agent.yaml ... OK
  runtime: agentcore
  model: ${MODEL_ID} via bedrock
  tools: 0 MCP target(s)
  memory: none
  identity: none
  observability: enabled

All blueprints valid.
```

If validation fails, the CLI reports the field path and the expected type or value. Fix each issue before proceeding.

---

## What Comes Next

Blueprint validation confirms the YAML is structurally correct. To run the agent end-to-end:

1. **Domain repo** — Scaffold a full project with `create-domain.sh`. See [Create a Domain Repo]({{ '/docs/getting-started/create-domain-repo' | relative_url }}).
2. **Infrastructure** — Deploy the platform Terraform modules (Gateway, Memory, Runtime, Identity, Observability). See [Infrastructure]({{ '/docs/infrastructure/' | relative_url }}).
3. **Handler** — Write a prompt builder and a 5-line handler. See [First Agent]({{ '/docs/getting-started/first-agent' | relative_url }}).
4. **Deploy** — `agentcli deploy agent blueprints/agents/my-agent.yaml --env dev` builds the container, pushes to ECR, and registers the Runtime.

---

## Next Steps

- [Installation]({{ '/docs/getting-started/installation' | relative_url }}) — full package reference, optional extras, and all environment variables
- [First Agent]({{ '/docs/getting-started/first-agent' | relative_url }}) — complete step-by-step tutorial with memory, tools, and policy
- [Inference Providers]({{ '/docs/inference/' | relative_url }}) — Bedrock, LiteLLM, Anthropic, and Vertex configuration
- [Agent Blueprint Spec]({{ '/docs/blueprints/agent-blueprint' | relative_url }}) — every field documented
