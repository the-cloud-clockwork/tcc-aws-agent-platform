---
title: Installation
nav_order: 2
parent: Getting Started
---

# Installation

Full reference for all SDK packages, optional extras, the CLI, Terraform module wiring, and the environment variables the platform reads at runtime.

---

## Package Index

> **Package availability — not on PyPI.** `agent-core`, `agent-cli`, `prompt-registry`, and `mcp-artifacts` are published to a **private AWS CodeArtifact registry** and are **not yet available on PyPI**. External users without CodeArtifact access should install directly from source:
> ```bash
> git clone https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform.git
> cd tcc-aws-agent-platform
> pip install -e "core/"        # agent-core
> pip install -e "cli/"         # agent-cli
> pip install -e "prompts/"     # prompt-registry
> pip install -e "artifacts/"   # mcp-artifacts
> ```
> A public distribution channel (PyPI or GitHub Packages) is planned but not yet available. Organizations with CodeArtifact access: configure your index URL below.

Configure pip to point at your organization's registry before installing:

```bash
pip config set global.index-url "<your-org-package-index-url>"
```

If your organization uses AWS CodeArtifact, obtain a short-lived auth token and configure the index URL:

```bash
CODEARTIFACT_AUTH_TOKEN=$(aws codeartifact get-authorization-token \
  --domain <domain> \
  --domain-owner <account-id> \
  --query authorizationToken --output text)

pip config set global.index-url \
  "https://aws:${CODEARTIFACT_AUTH_TOKEN}@<domain>-<account-id>.d.codeartifact.<region>.amazonaws.com/pypi/<repo>/simple/"
```

Replace `<domain>`, `<account-id>`, `<region>`, and `<repo>` with the values for your organization's CodeArtifact domain.

---

## SDK Packages

The platform is distributed as four Python packages. Install only what your domain repo needs.

| Package | Install Command | Purpose |
|---------|----------------|---------|
| `agent-core` | `pip install agent-core` | Core runtime engine — BlueprintLoader, GenericHandler, Gateway, Memory, Identity, Policy, Observability, Evaluation, A2A, MCP base classes |
| `prompt-registry` | `pip install prompt-registry` | Versioned prompt management — S3 + DynamoDB storage, mode-gated resolution |
| `mcp-artifacts` | `pip install mcp-artifacts` | Artifact store — S3 + DynamoDB, CloudFront or S3 signed URL delivery, claim-check pattern |
| `agent-cli` | `pip install agent-cli` | CLI — blueprint validation, prompt management, strategy lifecycle, deployment |

### Optional Extras for `agent-core`

Install extras to enable provider-specific functionality:

```bash
# LiteLLM proxy / OpenAI-compatible endpoints
pip install "agent-core[litellm]"

# Direct Anthropic API
pip install "agent-core[anthropic]"

# Local PII filtering via Microsoft Presidio
pip install "agent-core[presidio]"

# Langfuse evaluation provider
pip install "agent-core[evaluation_langfuse]"

# In-process response caching via Redis
pip install "agent-core[cache]"
```

{: .note }
> The `litellm` extra pins `litellm>=1.83.0,<2`. Versions 1.82.7–1.82.8 contained a supply chain attack (CVE-2026-33634) and must not be used. The platform enforces this bound automatically when you install through this extra.

---

## Development Install

For platform contributors or domain teams that need to run tests against the SDK source:

```bash
git clone https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform.git
cd aws-agent-platform

pip install -e "core/[dev]"       # agent-core with test dependencies
pip install -e "prompts/[dev]"    # prompt-registry with test dependencies
pip install -e "artifacts/[dev]"  # mcp-artifacts with test dependencies
pip install -e "cli/[dev]"        # agent-cli with test dependencies
```

The `[dev]` extras install: `pytest`, `ruff`, `mypy`, `moto` (for AWS mocks), and all type stubs.

Run the test suite:

```bash
cd core && pytest
```

Lint and format:

```bash
ruff check .
ruff format --check .
```

---

## Terraform Module Setup

Infrastructure is consumed via Terraform modules referenced directly from the Git source. Domain repos do not copy the module files — they pin to a release tag.

### Deployment Order

Modules must be applied in order: `platform` → `agents` → `workflows`. The agents module requires outputs from platform, and the workflows module requires runtime ARNs from agents.

### Platform Module

Deploys the shared infrastructure stack once per AWS account and environment: security (5 KMS keys), data stores (6 DynamoDB tables, SQS), observability pipeline, API layer, and AgentCore Gateway and Memory.

The VPC and subnets are externally managed — pass them in as inputs:

```hcl
# infra/main.tf
module "platform" {
  source = "git::https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform//modules/platform?ref=v1.0.0"

  environment         = var.environment
  vpc_id              = var.vpc_id
  public_subnet_ids   = var.public_subnet_ids
  private_subnet_ids  = var.private_subnet_ids
  isolated_subnet_ids = var.isolated_subnet_ids

  # Optional feature flags
  enable_waf                    = true
  enable_cloudfront             = false
  guardrail_enabled             = false   # set true to enable Bedrock Guardrails
  enable_artifacts_gateway_target = true
}
```

### Agents Module

Deploys per-agent resources driven by your YAML blueprints (ECR repositories, IAM roles, Runtime registrations):

```hcl
module "agents" {
  source     = "git::https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform//modules/agents?ref=v1.0.0"
  depends_on = [module.platform]

  resource_prefix   = "${var.environment}-myapp"
  blueprints_dir    = "${path.module}/../blueprints/agents"
  source_dir        = "${path.root}/../agents"
  source_layout     = "monorepo"   # or "polyrepo" for per-service subdirs

  # Wire platform outputs
  gateway_id                   = module.platform.gateway_id
  memory_id                    = module.platform.memory_id
  vpc_id                       = module.platform.vpc_id
  private_subnet_ids           = module.platform.private_subnet_ids
  data_kms_key_arn             = module.platform.data_kms_key_arn
  artifacts_table_name         = module.platform.artifacts_table_name
  prompt_registry_function_arn = module.platform.prompt_registry_function_arn
  prompt_registry_function_name = module.platform.prompt_registry_function_name
  litellm_api_key              = var.litellm_api_key   # sensitive; injected as LITELLM_API_KEY
}
```

### Workflows Module

Deploys Step Functions state machines generated from workflow blueprint YAML files:

```hcl
module "workflows" {
  source     = "git::https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform//modules/workflows?ref=v1.0.0"
  depends_on = [module.agents]

  resource_prefix = "${var.environment}-myapp"
  blueprints_dir  = "${path.module}/../blueprints/workflows"
  runtime_arns    = module.agents.runtime_arns
}
```

### Initialize and Apply

```bash
cd infra/
terraform init
terraform plan -var-file=envs/dev.tfvars
terraform apply -var-file=envs/dev.tfvars
```

Key outputs after apply: `gateway_url`, `gateway_id`, `memory_id`, and SSM parameters under your configured `ssm_root_path` for cross-team consumption without Terraform state sharing.

---

## Environment Variables

Set these before running agents. Never hardcode values — all are read from the environment at startup.

### Always Required

| Variable | Description |
|----------|-------------|
| `AWS_REGION` | Primary AWS region for platform services |
| `GATEWAY_URL` | AgentCore Gateway endpoint — Terraform output |
| `AGENTCORE_MEMORY_ID` | AgentCore Memory resource ID — Terraform output (required when `memory.strategies` is declared) |
| `EXECUTION_MODE` | `simulation`, `staging`, or `production` — gates prompt variants and draft/stable prompt resolution |

### Provider-Specific

| Variable | Provider | Description |
|----------|----------|-------------|
| `BEDROCK_REGION` | `bedrock` | AWS region where Bedrock models are invoked (required for `provider: bedrock`) |
| `LITELLM_API_KEY` | `litellm` | API key for the LiteLLM proxy (typically injected by Terraform via `litellm_api_key` variable) |
| `ANTHROPIC_API_KEY` | `anthropic` | Anthropic API key (use `api_key_env: ANTHROPIC_API_KEY` in blueprint) |
| `GOOGLE_APPLICATION_CREDENTIALS` | `vertex` | Path to GCP service account credentials JSON |

### Observability

| Variable | Description |
|----------|-------------|
| `LANGFUSE_HOST` | Langfuse server URL (e.g. `https://langfuse.example.com`) |
| `LANGFUSE_PUBLIC_KEY` | Langfuse project public key |
| `LANGFUSE_SECRET_KEY` | Langfuse project secret key |
| `LANGFUSE_ENABLED` | Set to `false` to disable Langfuse without changing the blueprint (useful in local dev) |
| `BEDROCK_GUARDRAIL_ID` | Bedrock Guardrail ID (required when `data_protection.provider: bedrock`) |
| `BEDROCK_GUARDRAIL_VERSION` | Bedrock Guardrail version (required when `data_protection.provider: bedrock`) |
| `AUDIT_LOG_TABLE` | DynamoDB table name for audit log writes (default env var name; configurable via `audit_log.table_env` in blueprint) |

### Prompt Registry

| Variable | Description |
|----------|-------------|
| `PROMPT_REGISTRY_FUNCTION` | Lambda function name for direct boto3 invoke — the production resolution path |
| `PROMPT_REGISTRY_URL` | HTTP fallback URL (used when `PROMPT_REGISTRY_FUNCTION` is not set) |

### Runtime

| Variable | Description |
|----------|-------------|
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`) |
| `BLUEPRINTS_DIR` | Path to blueprint YAML files (default: `blueprints/`) |
| `A2A_PORT` | Port for the A2A sidecar server (default: from blueprint `runtime.a2a_port`; raises if 0) |

{: .note }
> `EXECUTION_MODE` is a first-class concept. Prompts, data sources, and execution targets resolve differently per mode. Always set it explicitly — never let it default.

---

## Linting

The SDK and CLI enforce `ruff` for linting and formatting. Run before committing:

```bash
ruff check .
ruff format --check .
```

---

## Next Steps

- [First Agent]({{ '/docs/getting-started/first-agent' | relative_url }}) — build and deploy your first agent end-to-end
- [Inference Providers]({{ '/docs/inference/' | relative_url }}) — full provider configuration reference
- [Infrastructure]({{ '/docs/infrastructure/' | relative_url }}) — Terraform module reference and deployment patterns
- [CLI Reference]({{ '/docs/cli/' | relative_url }}) — full `agentcli` command reference
