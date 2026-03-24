---
title: Installation
nav_order: 2
parent: Getting Started
grand_parent: Documentation
---

# Installation

Full installation reference for all SDK packages, the CLI, and the Terraform modules.

---

## SDK Packages

The platform is distributed as four Python packages. Install only what your domain repo needs.

| Package | Install Command | Purpose |
|---------|----------------|---------|
| `agent-core` | `pip install agent-core` | Core runtime engine -- BlueprintLoader, GenericHandler, Gateway, Memory, Identity, Policy, Observability, Evaluation, A2A, MCP base classes |
| `prompt-registry` | `pip install prompt-registry` | Versioned prompt management -- S3 + DynamoDB storage, mode-gated resolution |
| `mcp-artifacts` | `pip install mcp-artifacts` | Artifact store MCP server -- S3 + DynamoDB, signed URL delivery, claim-check pattern |
| `agent-cli` | `pip install agent-cli` | CLI tooling -- blueprint validation, prompt management, strategy lifecycle, deployment |

### Package Index

Packages are distributed through a private Python package repository. Configure your pip index URL according to your organization's package distribution setup before installing.

---

## Development Install

For platform contributors or domain teams that need to run tests locally against the SDK source:

```bash
git clone https://github.com/org/aws-agent-platform.git
cd aws-agent-platform

pip install -e "core/[dev]"       # agent-core with test dependencies
pip install -e "prompts/[dev]"    # prompt-registry with test dependencies
pip install -e "artifacts/[dev]"  # mcp-artifacts with test dependencies
pip install -e "cli/[dev]"        # agent-cli with test dependencies
```

The `[dev]` extras install: `pytest`, `ruff`, `mypy`, `moto` (for AWS mocks), and all type stubs.

---

## Terraform Module Setup

Infrastructure is consumed via Terraform modules. Domain repos reference the platform modules directly from the Git source.

### Platform Module

Deploys the shared infrastructure stack (network, security, data stores, observability, API layer, and AgentCore services). Deploy this once per AWS account and environment.

```hcl
# infra/main.tf
module "platform" {
  source = "git::https://github.com/org/aws-agent-platform//modules/platform?ref=v1.0.0"

  environment = var.environment
  vpc_id      = module.network.vpc_id

  # Optional -- override defaults
  enable_waf         = true
  enable_cloudfront  = false
}
```

### Agents Module

Deploys per-agent resources (ECR repositories, IAM roles, Runtime registrations) driven by your YAML blueprints.

```hcl
module "agents" {
  source = "git::https://github.com/org/aws-agent-platform//modules/agents?ref=v1.0.0"

  platform_outputs = module.platform.outputs
  blueprints_dir   = "./blueprints/agents/"
}
```

### Workflows Module

Deploys Step Functions state machines generated from workflow blueprint YAML files.

```hcl
module "workflows" {
  source = "git::https://github.com/org/aws-agent-platform//modules/workflows?ref=v1.0.0"

  platform_outputs = module.platform.outputs
  blueprints_dir   = "./blueprints/workflows/"
}
```

### Initialize and Plan

```bash
cd infra/
terraform init
terraform plan -var-file=envs/dev.tfvars
terraform apply -var-file=envs/dev.tfvars
```

The apply outputs `gateway_url`, `memory_id`, `cognito_pool_id`, and other values your agent runtime needs.

---

## Key Environment Variables

Set these in your deployment environment before running agents. Never hardcode values.

| Variable | Required | Description |
|----------|----------|-------------|
| `AWS_REGION` | Yes | Primary AWS region for platform services |
| `BEDROCK_REGION` | Yes | AWS region where Bedrock models are invoked (may differ from primary) |
| `GATEWAY_URL` | Yes | AgentCore Gateway endpoint -- output from Terraform |
| `MEMORY_ID` | Yes | AgentCore Memory resource ID -- output from Terraform |
| `COGNITO_POOL_ID` | Yes | Cognito User Pool ID for inbound JWT validation |
| `COGNITO_CLIENT_ID` | Yes | Cognito App Client ID for inbound JWT validation |
| `MODEL_ID` | Yes | Bedrock model ID for this agent (e.g., a specific Claude variant) |
| `EXECUTION_MODE` | Yes | `simulation`, `staging`, or `production` -- gates prompt variants and risk logic |
| `BLUEPRINTS_DIR` | No | Path to blueprint YAML files (default: `blueprints/`) |
| `LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`) |

{: .note }
> `EXECUTION_MODE` is a first-class concept in the platform. Prompts, data sources, and execution targets all resolve differently per mode. Always set it explicitly -- never let it default.

---

## Linting

The SDK and CLI enforce `ruff` formatting. Run before committing:

```bash
ruff check .
ruff format --check .
```

---

## Next Steps

- [First Agent]({{ '/docs/getting-started/first-agent' | relative_url }}) -- build and deploy your first agent end-to-end
- [Infrastructure]({{ '/docs/infrastructure/' | relative_url }}) -- Terraform module reference and deployment patterns
- [CLI Reference]({{ '/docs/cli/' | relative_url }}) -- full `agentcli` command reference
