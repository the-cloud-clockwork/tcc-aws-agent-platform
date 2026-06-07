---
title: "Infrastructure (Terraform)"
nav_order: 10
has_children: true
---

# Infrastructure (Terraform)

The AWS Agent Platform ships as seven composable Terraform modules — three **core modules** that you deploy for every environment, and four **utility modules** that the core modules use internally and that domain repos can reuse for their own Lambdas and S3 buckets.

All modules are consumed from a domain repository via a `git::` source reference. The platform itself does not need to be cloned — only referenced.

---

## Module Map

### Core Modules

| Module | Path | Purpose | Deploy order |
|--------|------|---------|--------------|
| **platform** | `modules/platform/` | Shared infrastructure: security groups, KMS keys, DynamoDB tables, S3 buckets, SQS, AgentCore Gateway + Memory, Cognito (optional), API Gateway, Prompt Registry Lambda | 1st |
| **agents** | `modules/agents/` | Per-agent resources driven by blueprint YAML — AgentCore Runtime, ECR, CodeBuild, IAM role, Gateway targets, Memory strategies, credential providers | 2nd |
| **workflows** | `modules/workflows/` | Per-workflow Step Functions state machines and EventBridge schedules driven by workflow blueprint YAML | 3rd |

### Utility Modules

| Module | Path | Purpose |
|--------|------|---------|
| **lambda** | `modules/lambda/` | Reusable Lambda — archive, function, IAM role, X-Ray, CloudWatch log group |
| **lambda\_alarms** | `modules/lambda_alarms/` | CloudWatch alarm pair (Errors + Duration p99) per Lambda |
| **scheduled\_lambda** | `modules/scheduled_lambda/` | EventBridge rule + target + Lambda permission triad |
| **s3\_encrypted\_bucket** | `modules/s3_encrypted_bucket/` | S3 bucket with versioning, KMS SSE, full public-access block, optional SSM export |

The utility modules are used internally by `modules/platform/` (for the Prompt Registry Lambda, artifact Lambda, and all platform buckets), and are available for domain repos to use directly.

---

## Platform Sub-Modules

The `modules/platform/` module is composed of six sub-modules that wire together automatically. Domain repos consume `modules/platform/` as a single unit — the sub-module boundaries are an implementation detail.

| Sub-Module | Path | What It Provisions |
|------------|------|--------------------|
| **security** | `modules/platform/modules/security` | Five KMS keys (data, storage, secrets, platform\_artifacts, domain\_artifacts); WAF WebACL (optional); Bedrock Guardrail (optional) |
| **data** | `modules/platform/modules/data` | Six DynamoDB tables (artifacts, audit\_log, prompt\_registry, run\_history, idempotency, evaluation); S3 buckets (platform artifacts, domain artifacts, prompt registry, CodeBuild source); SQS artifact-notifications queue + DLQ; CloudFront distribution (optional) |
| **observability** | `modules/platform/modules/observability` | CloudWatch log groups; SNS alert topic; X-Ray group; CloudWatch dashboard |
| **api** | `modules/platform/modules/api` | API Gateway HTTP API; artifacts MCP Lambda; shared Lambda layer |
| **agentcore** | `modules/platform/modules/agentcore` | AgentCore Gateway (KMS-encrypted, Cedar policy engine); AgentCore Memory; Cognito user pool + M2M client (optional); OAuth2 credential provider for MCP targets (optional); Code Interpreter built-in tool (optional); Browser built-in tool (optional) |
| **prompt\_registry** | `modules/platform/modules/prompt_registry` | Prompt Registry Lambda (Function URL) backed by the data module's DynamoDB table + S3 bucket |

Security groups for agent runtimes and MCP servers are provisioned directly in `modules/platform/main.tf` (not in a sub-module) and exposed as `agent_security_group_id` and `mcp_security_group_id` outputs.

> **Networking is externally managed.** The platform module does **not** create a VPC. It accepts `vpc_id`, `public_subnet_ids`, `private_subnet_ids`, and `isolated_subnet_ids` as inputs from a separately managed networking project. This is intentional — VPC lifecycle and agent platform lifecycle are independent concerns.

---

## Deployment Order

```
modules/platform   ──►  modules/agents   ──►  modules/workflows
    (Phase 1)              (Phase 2a)              (Phase 2b)
```

- **Phase 1** provisions the shared foundation and emits outputs consumed by Phases 2a and 2b.
- **Phase 2a** (agents) must complete before Phase 2b because workflows need `module.agents.runtime_arns`.
- Phases 2a and 2b both depend on Phase 1, but can otherwise be applied in any order once Phase 1 is complete.

A typical root module wires all three together:

```hcl
module "platform" {
  source = "git::https://github.com/your-org/aws-agent-platform.git//modules/platform?ref=v1.0.0"

  # Networking (externally managed)
  vpc_id              = var.vpc_id
  private_subnet_ids  = var.private_subnet_ids
  public_subnet_ids   = var.public_subnet_ids
  isolated_subnet_ids = var.isolated_subnet_ids

  environment     = var.environment
  resource_prefix = "myplatform"
  aws_region      = var.aws_region
  bedrock_region  = var.bedrock_region
  ssm_root_path   = "/myplatform/${var.environment}"
}

module "agents" {
  source     = "git::https://github.com/your-org/aws-agent-platform.git//modules/agents?ref=v1.0.0"
  depends_on = [module.platform]

  blueprint_dir        = "${path.module}/blueprints/agents"
  gateway_targets_file = "${path.module}/blueprints/gateway-targets.yaml"

  gateway_id              = module.platform.gateway_id
  gateway_url             = module.platform.gateway_url
  gateway_role_arn        = module.platform.gateway_role_arn
  memory_id               = module.platform.memory_id
  vpc_id                  = module.platform.vpc_id
  private_subnet_ids      = module.platform.private_subnet_ids
  agent_security_group_id = module.platform.agent_security_group_id
  storage_kms_key_arn     = module.platform.storage_kms_key_arn
  codebuild_source_bucket = module.platform.codebuild_source_bucket

  prompt_registry_url          = module.platform.prompt_registry_url
  prompt_registry_function_arn = module.platform.prompt_registry_function_arn

  environment     = var.environment
  resource_prefix = "myplatform"
  aws_region      = var.aws_region
  ssm_root_path   = "/myplatform/${var.environment}"
}

module "workflows" {
  source     = "git::https://github.com/your-org/aws-agent-platform.git//modules/workflows?ref=v1.0.0"
  depends_on = [module.agents]

  workflow_dir       = "${path.module}/blueprints/workflows"
  agent_runtime_arns = module.agents.runtime_arns

  environment     = var.environment
  resource_prefix = "myplatform"
  aws_region      = var.aws_region
  ssm_root_path   = "/myplatform/${var.environment}"
}
```

---

## Monorepo vs Polyrepo Source Layout

The agents module supports two build source layouts, controlled by `source_layout`:

| Layout | Value | Dockerfile location | When to use |
|--------|-------|---------------------|-------------|
| **Monorepo** | `"monorepo"` (default) | Single `Dockerfile` at `source_dir` root | All agents live in one repo |
| **Polyrepo** | `"polyrepo"` | `source_dir/<agent-id>/Dockerfile` (suffix stripped via `polyrepo_suffix`) | Each agent or MCP server is its own repo |

For polyrepo layouts, the module strips the `polyrepo_suffix` (default `"-mcp"`) from each blueprint `id` to derive the subdirectory name. A blueprint with `id: analytics-mcp` would map to `source_dir/analytics/Dockerfile`.

---

## Cross-Module Interface via SSM

All platform outputs are also written as SSM parameters under `var.ssm_root_path`. This means downstream modules and domain tooling can read platform outputs **without Terraform state sharing**:

```bash
# Read the Gateway URL without accessing Terraform state
aws ssm get-parameter \
  --name "/myplatform/dev/agentcore/gateway-url" \
  --query "Parameter.Value" --output text
```

Key SSM paths published by the platform module:

| SSM Path (relative to `ssm_root_path`) | Value |
|----------------------------------------|-------|
| `/network/vpc-id` | VPC ID |
| `/agentcore/gateway-url` | AgentCore Gateway MCP endpoint |
| `/agentcore/gateway-id` | AgentCore Gateway ID |
| `/agentcore/memory-id` | AgentCore Memory ID |
| `/tables/<name>/name` | DynamoDB table name (per table) |
| `/tables/<name>/arn` | DynamoDB table ARN (per table) |
| `/buckets/<name>/name` | S3 bucket name (per bucket) |
| `/prompt-registry/url` | Prompt Registry Lambda Function URL |
| `/api/artifacts-api-url` | Artifact store API Gateway URL |
| `/observability/alert-topic-arn` | SNS alert topic ARN |
| `/cdn/cloudfront-domain` | CloudFront domain (when enabled) |

---

## Shared Design Principles

**Blueprint-driven scaling.** The `agents` and `workflows` modules use `for_each` over YAML files. Adding a new agent or workflow means dropping a YAML file — no Terraform code changes.

**Envelope encryption.** Five KMS keys cover every data tier. AES256 is never used in place of KMS.

**Conditional resources.** WAF, CloudFront, Cognito, Bedrock Guardrail, and built-in tools are all gated by boolean variables. Nothing is created unconditionally.

**Least-privilege IAM.** Permissions are scoped to specific ARNs where the API allows it. The per-agent IAM role trust policy is restricted by both `aws:SourceAccount` (exact account match) and `aws:SourceArn` (prefix match on the account's AgentCore ARN space).

---

## Pages in This Section

| Page | Description |
|------|-------------|
| [Platform Module](./platform-module) | Sub-modules, variables, outputs, and usage for `modules/platform/` |
| [Agents Module](./agents-module) | Blueprint-driven agent deployment — Runtime, ECR, IAM, Gateway targets |
| [Workflows Module](./workflows-module) | Step Functions generation from workflow blueprint YAML |
| [Utility Modules](./utility-modules) | Four reusable building-block modules: lambda, lambda\_alarms, scheduled\_lambda, s3\_encrypted\_bucket |
| [Prompt Registry Module](./prompt-registry-module) | Versioned prompt management — Lambda, DynamoDB, S3 |
| [Deployment Patterns](./deployment-patterns) | Environment strategy, full deployment sequence, cross-region Bedrock, state management |
