---
title: Agents Module
nav_order: 2
parent: "Infrastructure (Terraform)"
---

# Agents Module

The agents module (`modules/agents/`) reads agent blueprint YAML files and creates all AWS resources required to run each agent. It uses a `for_each` pattern driven entirely by blueprint files — adding a new agent requires only dropping a YAML file in the blueprint directory. No Terraform code changes are needed.

---

## How Blueprint-Driven Deployment Works

The module scans the `blueprint_dir` directory for `*.yaml` files at plan time:

```hcl
# locals.tf — simplified
blueprint_files = fileset(var.blueprint_dir, "*.yaml")

blueprints = {
  for f in local.blueprint_files :
  yamldecode(file("${var.blueprint_dir}/${f}")).id => yamldecode(file("${var.blueprint_dir}/${f}"))
}
```

The blueprint `id` field becomes the map key. Every resource in the module iterates over this map:

```hcl
resource "aws_ecr_repository" "agent" {
  for_each = local.blueprints
  name     = "${local.name_prefix}-${each.key}"
}
```

This means `terraform plan` sees exactly one set of resources per blueprint file. Removing a YAML file removes the corresponding resources on the next apply.

---

## Resources Provisioned Per Agent

| Resource | Count | Driven By |
|----------|-------|-----------|
| `aws_cloudwatch_log_group` | 1 per agent | Blueprint `id` |
| `aws_cloudwatch_log_delivery_source` | 1 per agent | Runtime ARN |
| `aws_cloudwatch_log_delivery_destination` | 1 per agent | Log group ARN |
| `aws_cloudwatch_log_delivery` | 1 per agent | Source → destination link |
| `aws_iam_role` | 1 per agent | Blueprint `id` |
| `aws_ecr_repository` | 1 per agent | Blueprint `id` |
| `aws_codebuild_project` | 1 per agent | Blueprint `id` |
| `aws_bedrockagentcore_agent_runtime` | 1 per agent | Blueprint `id` + `runtime:` block |
| `aws_bedrockagentcore_agent_runtime_endpoint` | 1 per agent | Blueprint `id` |
| Gateway targets | 0–N per agent | `gateway_targets_file` (shared) |
| `aws_bedrockagentcore_memory_strategy` | 0–N per agent | `memory.strategies` array |
| API key credential providers | 0–N per agent | `identity.credentials` (api\_key type) |
| OAuth2 credential providers | 0–N per agent | `identity.credentials` (oauth2 type) |
| `aws_ssm_parameter` | 3 per agent | Runtime ARN, ECR URL, endpoint URL |

---

## Gateway Target Authentication

Gateway targets use different credential strategies depending on the target type:

| Target Type | Credential Method | Description |
|-------------|-------------------|-------------|
| Lambda | `gateway_iam_role` | Gateway uses its IAM role to invoke Lambda. No token exchange required. |
| MCP Server (Runtime) | OAuth2 | Gateway retrieves an M2M access token via Cognito and injects it as a Bearer token. |
| OpenAPI | `gateway_iam_role` or OAuth2 | Depends on the target's auth requirements. |

**Lambda targets** always use `gateway_iam_role`. The Gateway IAM role has scoped `lambda:InvokeFunction` permission.

**MCP server targets** (blueprints with `protocol: MCP`) attach an OAuth2 credential block when `mcp_oauth2_provider_arn` is set. When that variable is empty, MCP server targets fall back to `gateway_iam_role`.

**MCP Runtime JWT authorizer** — when `mcp_oauth2_discovery_url` is set, MCP protocol Runtimes are configured with a `custom_jwt_authorizer` that validates incoming Bearer tokens. Only requests bearing a valid M2M token from the Gateway can reach the MCP server. The authorizer validates the OIDC discovery URL and the `aud` claim against `mcp_oauth2_allowed_clients`.

---

## Runtime Environment Variables

Each AgentCore Runtime is created with platform outputs wired as environment variables. Variables are injected conditionally — only when the corresponding input is non-empty:

| Environment Variable | Source | Condition |
|---------------------|--------|-----------|
| `AGENTCORE_GATEWAY_URL` | `var.gateway_url` | Always |
| `AGENTCORE_MEMORY_ID` | `var.memory_id` | Always |
| `EXECUTION_MODE` | `var.execution_mode` | When non-empty (domain-defined semantics) |
| `AGENT_ID` | Blueprint `id` | Always |
| `AWS_DEFAULT_REGION` | `var.aws_region` | Always |
| `SSM_ROOT_PATH` | `var.ssm_root_path` | Always |
| `BEDROCK_REGION` | `var.bedrock_region` | When non-empty |
| `ARTIFACTS_BUCKET` | `var.artifacts_bucket_name` | When non-empty |
| `PROMPT_REGISTRY_URL` | `var.prompt_registry_url` | When non-empty |
| `PROMPT_REGISTRY_FUNCTION` | `var.prompt_registry_function_arn` | When non-empty |
| `LITELLM_API_KEY` | `var.litellm_api_key` (sensitive) | When non-empty |
| `LANGFUSE_PUBLIC_KEY` | `var.langfuse_public_key` | When non-empty |
| `LANGFUSE_SECRET_KEY` | `var.langfuse_secret_key` (sensitive) | When non-empty |
| `LANGFUSE_HOST` | `var.langfuse_host` | When non-empty |
| `BEDROCK_GUARDRAIL_ID` | `var.guardrail_id` | When non-empty |
| `BEDROCK_GUARDRAIL_VERSION` | `var.guardrail_version` | When non-empty |
| `EVALUATION_TABLE` | `var.evaluation_table_name` | When non-empty |
| *(extra vars)* | `var.extra_environment_variables` | Merged for all runtimes |

> **`EXECUTION_MODE` note.** This is passed via `var.execution_mode`, which defaults to empty and is set independently of `var.environment`. Domain repos supply the execution mode string (e.g. `"simulation"`, `"production"`). It is not derived from the environment name.

---

## Input Variables

### Required

| Variable | Type | Description |
|----------|------|-------------|
| `environment` | `string` | Deployment environment |
| `resource_prefix` | `string` | Resource name prefix |
| `aws_region` | `string` | Primary AWS region |
| `ssm_root_path` | `string` | Root SSM path for parameter outputs |
| `blueprint_dir` | `string` | Path to directory containing agent YAML blueprints |
| `gateway_id` | `string` | AgentCore Gateway ID (from platform module) |
| `gateway_url` | `string` | AgentCore Gateway URL (from platform module) |
| `gateway_role_arn` | `string` | Gateway IAM role ARN (from platform module) |
| `memory_id` | `string` | AgentCore Memory ID (from platform module) |
| `vpc_id` | `string` | VPC ID (from platform module) |
| `private_subnet_ids` | `list(string)` | Private subnet IDs for VPC network mode |
| `agent_security_group_id` | `string` | Security group ID for agent containers |

### Platform Wiring (optional)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `storage_kms_key_arn` | `string` | `""` | KMS key for ECR encryption |
| `data_kms_key_arn` | `string` | `""` | KMS key for DynamoDB access |
| `platform_artifacts_kms_key_arn` | `string` | `""` | KMS key for platform artifact encryption |
| `domain_artifacts_kms_key_arn` | `string` | `""` | KMS key for domain artifact encryption |
| `artifacts_bucket_name` | `string` | `""` | Artifacts bucket name |
| `artifacts_bucket_arn` | `string` | `""` | Artifacts bucket ARN |
| `codebuild_source_bucket` | `string` | `""` | S3 bucket for agent source code uploads |
| `prompt_registry_url` | `string` | `""` | Prompt Registry Lambda Function URL |
| `prompt_registry_function_arn` | `string` | `""` | Prompt Registry Lambda ARN (for IAM grant) |
| `extra_s3_read_bucket_arns` | `list(string)` | `[]` | Additional S3 bucket ARNs to grant read access |
| `evaluation_table_name` | `string` | `""` | Evaluation results DynamoDB table name |
| `idempotency_table_name` | `string` | `""` | Idempotency DynamoDB table name |

### MCP / Cognito

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `mcp_oauth2_provider_arn` | `string` | `""` | OAuth2 credential provider ARN for MCP server Gateway targets |
| `mcp_oauth2_scopes` | `list(string)` | `[]` | OAuth2 scopes for MCP server Gateway targets |
| `mcp_oauth2_discovery_url` | `string` | `""` | OIDC discovery URL for MCP Runtime JWT authorizer |
| `mcp_oauth2_allowed_clients` | `list(string)` | `[]` | Allowed OAuth2 client IDs for MCP Runtime JWT authorizer |
| `cognito_token_url` | `string` | `""` | Cognito token endpoint (gateway\_direct\_mcp mode) |
| `cognito_mcp_client_id` | `string` | `""` | Cognito M2M client ID (gateway\_direct\_mcp mode) |
| `cognito_mcp_client_secret` | `string` | `""` | Cognito M2M client secret (sensitive; gateway\_direct\_mcp mode) |
| `cognito_mcp_scopes` | `string` | `""` | OAuth2 scopes for direct MCP auth (comma-separated) |
| `gateway_direct_mcp` | `bool` | `false` | Bypass Gateway for MCP calls (see note below) |
| `mcp_direct_urls` | `map(string)` | `{}` | MCP server name → direct runtime URL map (gateway\_direct\_mcp only) |

> **`gateway_direct_mcp` note.** This variable enables a workaround for AWS Issue #809, where the Gateway's `tools/call` path for MCP Runtime targets does not behave correctly. When `true`, agents call MCP servers directly using Cognito M2M tokens instead of routing through the Gateway. This is a temporary workaround; the variable and its associated logic will be removed once the upstream issue is resolved.

### Observability

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `observability_enabled` | `bool` | `true` | Inject OTEL env vars for CloudWatch GenAI Observability |
| `observability_log_group_prefix` | `string` | `/aws/bedrock-agentcore/runtimes/` | CloudWatch log group prefix (agent ID appended) |
| `observability_metric_namespace` | `string` | `bedrock-agentcore` | CloudWatch metric namespace for OTEL metrics |
| `langfuse_public_key` | `string` | `""` | Langfuse public key |
| `langfuse_secret_key` | `string` | `""` | Langfuse secret key (sensitive) |
| `langfuse_host` | `string` | `""` | Langfuse host URL |
| `log_retention_days` | `number` | `14` | CloudWatch log group retention |

### Guardrail

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `guardrail_id` | `string` | `""` | Bedrock Guardrail ID → `BEDROCK_GUARDRAIL_ID` env var |
| `guardrail_version` | `string` | `""` | Bedrock Guardrail version → `BEDROCK_GUARDRAIL_VERSION` env var |

### Build

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `source_dir` | `string` | `""` | Agent source code root directory |
| `source_layout` | `string` | `"monorepo"` | `"monorepo"` or `"polyrepo"` (see [Infrastructure landing](../infrastructure#monorepo-vs-polyrepo-source-layout)) |
| `polyrepo_suffix` | `string` | `"-mcp"` | Suffix stripped from blueprint ID to derive subdirectory name (polyrepo only) |
| `build_enabled` | `bool` | `false` | Build Docker images on `terraform apply` |
| `build_services` | `map(bool)` | `{}` | Per-service build override (empty = build all when `build_enabled=true`) |
| `extra_build_deps` | `map(string)` | `{}` | Extra dirs for polyrepo builds |

### General

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `bedrock_region` | `string` | `""` | Bedrock model access region → `BEDROCK_REGION` env var |
| `execution_mode` | `string` | `""` | Execution mode string → `EXECUTION_MODE` env var |
| `extra_environment_variables` | `map(string)` | `{}` | Arbitrary env vars merged into every runtime (domain-specific overrides) |
| `codeartifact_domain` | `string` | `""` | CodeArtifact domain for package resolution during builds |
| `codeartifact_repo` | `string` | `""` | CodeArtifact repository name for Python packages |
| `tags` | `map(string)` | `{}` | Additional resource tags |

---

## Outputs

| Output | Type | Description |
|--------|------|-------------|
| `runtime_arns` | `map(string)` | `agent_id` → AgentCore Runtime ARN |
| `runtime_names` | `map(string)` | `agent_id` → AgentCore Runtime name |
| `ecr_repository_urls` | `map(string)` | `agent_id` → ECR repository URL |
| `agent_ids` | `list(string)` | All agent IDs parsed from blueprint YAML |
| `runtime_endpoint_urls` | `map(string)` | `agent_id` → Runtime Endpoint URL |
| `mcp_runtime_authorizer_status` | `map(object)` | Per-Runtime authorizer state: protocol, `has_authorizer` bool, discovery URL. Designed for CI drift detection — see below. |

### `mcp_runtime_authorizer_status`

This output exposes per-runtime JWT authorizer attachment state for CI drift detection. The Gateway silently omits the authorizer when `mcp_oauth2_discovery_url` was empty at Runtime creation time, and this is not visible in the AWS console without clicking into each Runtime individually.

```bash
# Check after every apply to confirm MCP Runtimes have their authorizer attached
terraform output -json mcp_runtime_authorizer_status | jq '
  to_entries[] |
  select(.value.protocol == "MCP") |
  {runtime: .key, has_authorizer: .value.has_authorizer}
'
```

A `has_authorizer: false` on a Runtime with `protocol: MCP` indicates drift — the JWT authorizer is missing and unauthenticated requests can reach the MCP server.

---

## IAM Role — Per-Agent

Each agent gets a dedicated IAM role with a trust policy scoped to the `bedrock-agentcore.amazonaws.com` service principal, restricted by both `aws:SourceAccount` (exact account match) and `aws:SourceArn` (prefix match on the account's AgentCore ARN space). This prevents cross-account privilege escalation.

CloudWatch Logs permissions are scoped to the agent's own log group ARN prefixes. S3, DynamoDB, KMS, Lambda, and SSM permissions are added conditionally — only when the corresponding input variables are non-empty. ECR pull is scoped to the agent's own ECR repository ARN.

---

## Usage Example

```hcl
module "agents" {
  source = "git::https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform.git//modules/agents?ref=v1.0.0"

  environment     = var.environment
  resource_prefix = "myplatform"
  aws_region      = var.aws_region
  bedrock_region  = var.bedrock_region
  ssm_root_path   = "/myplatform/${var.environment}"

  # Blueprint source
  blueprint_dir        = "${path.module}/blueprints/agents"
  gateway_targets_file = "${path.module}/blueprints/gateway-targets.yaml"

  # Platform module outputs
  gateway_id              = module.platform.gateway_id
  gateway_url             = module.platform.gateway_url
  gateway_role_arn        = module.platform.gateway_role_arn
  memory_id               = module.platform.memory_id
  vpc_id                  = module.platform.vpc_id
  private_subnet_ids      = module.platform.private_subnet_ids
  agent_security_group_id = module.platform.agent_security_group_id
  storage_kms_key_arn     = module.platform.storage_kms_key_arn
  codebuild_source_bucket = module.platform.codebuild_source_bucket
  data_kms_key_arn        = module.platform.data_kms_key_arn

  # Prompt Registry
  prompt_registry_url          = module.platform.prompt_registry_url
  prompt_registry_function_arn = module.platform.prompt_registry_function_arn

  # MCP OAuth2 (conditional on cognito_enabled)
  mcp_oauth2_provider_arn    = module.platform.mcp_oauth2_provider_arn
  mcp_oauth2_scopes          = module.platform.mcp_oauth2_scopes
  mcp_oauth2_discovery_url   = module.platform.mcp_oauth2_discovery_url
  mcp_oauth2_allowed_clients = module.platform.mcp_oauth2_allowed_clients

  # Observability
  langfuse_host       = var.langfuse_host
  langfuse_public_key = var.langfuse_public_key
  langfuse_secret_key = var.langfuse_secret_key   # read from SSM, never hardcode

  tags = {
    Project   = "my-agent-platform"
    ManagedBy = "Terraform"
  }
}
```

---

## ECR Push Workflow

Each agent has a CodeBuild project configured for ARM64 (Graviton) builds. Upload source, trigger the build, and the Runtime picks up the new image:

```bash
# Upload source
aws s3 cp agent-source.zip \
  s3://$(terraform output -raw codebuild_source_bucket)/agents/my-agent/source.zip

# Trigger build
aws codebuild start-build \
  --project-name myplatform-dev-my-agent
```

See [Deployment Patterns](./deployment-patterns) for the full build and image-push sequence.

---

## Adding a New Agent

1. Create a YAML file in `blueprint_dir` (e.g. `blueprints/agents/classifier.yaml`) with a unique `id`.
2. Run `terraform plan` — Terraform shows the new ECR repository, Runtime, IAM role, and log group.
3. Run `terraform apply`.
4. Push the container image to the new ECR repository.
5. The Runtime is immediately available for invocation.

No Terraform code changes are required.
