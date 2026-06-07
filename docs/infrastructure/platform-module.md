---
title: Platform Module
nav_order: 1
parent: "Infrastructure (Terraform)"
---

# Platform Module

The platform module (`modules/platform/`) provisions the shared infrastructure that all agents and workflows depend on. It is the first module deployed in every environment and emits outputs consumed by the agents and workflows modules.

The module is composed of **six sub-modules** that wire together automatically. Domain repos consume `modules/platform/` as a single unit — the internal sub-module boundaries are an implementation detail.

> **Networking is externally managed.** This module does **not** create a VPC, subnets, NAT gateways, or route tables. Pass your existing VPC and subnet IDs as input variables (`vpc_id`, `private_subnet_ids`, `public_subnet_ids`, `isolated_subnet_ids`). Security groups for agent runtimes and MCP servers are created by the platform module directly and exposed as outputs.

---

## Sub-Modules

| Sub-Module | Path | What It Provisions |
|------------|------|--------------------|
| **security** | `modules/platform/modules/security` | Five KMS keys (data, storage, secrets, platform\_artifacts, domain\_artifacts); WAF WebACL (conditional); Secrets Manager observability secret; Bedrock Guardrail (conditional) |
| **data** | `modules/platform/modules/data` | Six DynamoDB tables (artifacts, audit\_log, prompt\_registry, run\_history, idempotency, evaluation); S3 buckets; SQS artifact-notifications queue + DLQ; CloudFront distribution (conditional) |
| **observability** | `modules/platform/modules/observability` | CloudWatch log groups; SNS alert topic; X-Ray group; CloudWatch dashboard |
| **api** | `modules/platform/modules/api` | API Gateway HTTP API; artifacts MCP Lambda; shared Lambda layer (pydantic, mcp\_artifacts) |
| **agentcore** | `modules/platform/modules/agentcore` | AgentCore Gateway (KMS-encrypted, Cedar policy engine); AgentCore Memory; Cognito user pool + M2M client (conditional); OAuth2 credential provider for MCP targets (conditional); Code Interpreter built-in tool (conditional); Browser built-in tool (conditional) |
| **prompt\_registry** | `modules/platform/modules/prompt_registry` | Prompt Registry Lambda (IAM-authenticated Function URL) backed by the data module's DynamoDB table and S3 bucket |

---

## Input Variables

### Required

| Variable | Type | Description |
|----------|------|-------------|
| `environment` | `string` | Deployment environment: `dev`, `staging`, or `production` |
| `resource_prefix` | `string` | Prefix for all resource names |
| `aws_region` | `string` | Primary AWS region |
| `bedrock_region` | `string` | Region for Bedrock model access (may differ from primary) |
| `ssm_root_path` | `string` | Root SSM parameter path (e.g. `/myplatform/dev`) |
| `vpc_id` | `string` | ID of the externally-managed VPC |
| `private_subnet_ids` | `list(string)` | Private subnet IDs (at least one required) |

### Networking (optional)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `public_subnet_ids` | `list(string)` | `[]` | Public subnet IDs |
| `isolated_subnet_ids` | `list(string)` | `[]` | Isolated subnet IDs (no internet access) |

### Security

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `kms_key_deletion_window_days` | `number` | `30` | KMS key deletion window in days |
| `waf_enabled` | `bool` | `false` | Enable WAF WebACL (attached to API Gateway and CloudFront) |
| `waf_rate_limit` | `number` | `1000` | WAF rate-limit rule threshold (requests per 5 minutes) |
| `waf_ip_whitelist` | `list(string)` | `[]` | IP CIDRs to allowlist in WAF |
| `guardrail_enabled` | `bool` | `false` | Provision a Bedrock Guardrail for PII/content protection |
| `guardrail_pii_entities` | `list(object)` | See below | PII entity types and actions for the guardrail |

Default `guardrail_pii_entities`: `EMAIL→ANONYMIZE`, `PHONE→ANONYMIZE`, `NAME→ANONYMIZE`, `US_SOCIAL_SECURITY_NUMBER→BLOCK`, `CREDIT_DEBIT_CARD_NUMBER→BLOCK`.

### Data

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `dynamodb_billing_mode` | `string` | `"PAY_PER_REQUEST"` | `PAY_PER_REQUEST` or `PROVISIONED` |
| `dynamodb_read_capacity` | `number` | `25` | Read capacity units (PROVISIONED mode only) |
| `dynamodb_write_capacity` | `number` | `10` | Write capacity units (PROVISIONED mode only) |
| `cloudfront_enabled` | `bool` | `true` | Enable CloudFront distribution for artifact delivery |
| `removal_policy_destroy` | `bool` | `true` | `true` for dev (destroy on removal), `false` for staging/production (retain) |

### AgentCore

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `gateway_auth_type` | `string` | `"AWS_IAM"` | Gateway inbound auth: `AWS_IAM`, `CUSTOM_JWT`, or `NONE` |
| `gateway_jwt_discovery_url` | `string` | `""` | OIDC discovery URL (CUSTOM\_JWT mode only) |
| `gateway_jwt_allowed_clients` | `list(string)` | `[]` | Allowed JWT client IDs (CUSTOM\_JWT mode only) |
| `memory_event_expiry_days` | `number` | `30` | AgentCore Memory short-term event retention in days |
| `memory_description` | `string` | `""` | Description for the AgentCore Memory resource |
| `cognito_enabled` | `bool` | `false` | Provision Cognito user pool and M2M app client |
| `builtin_browser_enabled` | `bool` | `false` | Provision AgentCore Browser built-in tool |
| `builtin_code_interpreter_enabled` | `bool` | `false` | Provision AgentCore Code Interpreter built-in tool |
| `enable_artifacts_gateway_target` | `bool` | `true` | Register the artifacts MCP Lambda as a Gateway target |

### Observability

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `log_retention_days` | `number` | `14` | CloudWatch log group retention |
| `sns_alert_email` | `string` | `""` | Email address for SNS alert subscriptions |

### API

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `api_throttle_rate` | `number` | `100` | API Gateway throttle rate limit (requests/sec) |
| `api_throttle_burst` | `number` | `200` | API Gateway throttle burst limit |
| `api_cors_origins` | `list(string)` | `[]` | Allowed CORS origins for the artifact API |

### General

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `tags` | `map(string)` | `{}` | Additional resource tags merged with platform defaults |

---

## Outputs

### Network

| Output | Description |
|--------|-------------|
| `vpc_id` | VPC ID (pass-through from input) |
| `public_subnet_ids` | Public subnet IDs (pass-through) |
| `private_subnet_ids` | Private subnet IDs (pass-through) |
| `isolated_subnet_ids` | Isolated subnet IDs (pass-through) |
| `agent_security_group_id` | Security group ID for agent runtime containers |
| `mcp_security_group_id` | Security group ID for MCP server containers |

### Security

| Output | Description |
|--------|-------------|
| `platform_artifacts_kms_key_arn` | KMS key ARN for platform artifact encryption |
| `domain_artifacts_kms_key_arn` | KMS key ARN for domain artifact encryption |
| `data_kms_key_arn` | KMS key ARN for DynamoDB and AgentCore resources |
| `storage_kms_key_arn` | KMS key ARN for S3 and ECR encryption |
| `secrets_kms_key_arn` | KMS key ARN for Secrets Manager encryption |
| `waf_acl_arn` | WAF WebACL ARN (empty string when WAF is disabled) |
| `guardrail_id` | Bedrock Guardrail ID (empty when disabled) |
| `guardrail_version` | Published Bedrock Guardrail version (empty when disabled) |

### Data

| Output | Description |
|--------|-------------|
| `table_names` | Map of table key → DynamoDB table name (`artifacts`, `audit_log`, `prompt_registry`, `run_history`, `idempotency`, `evaluation`) |
| `table_arns` | Map of table key → DynamoDB table ARN |
| `artifacts_bucket_name` | Artifacts S3 bucket name |
| `artifacts_bucket_arn` | Artifacts S3 bucket ARN |
| `artifacts_table_name` | DynamoDB artifacts table name |
| `artifacts_table_arn` | DynamoDB artifacts table ARN |
| `bucket_names` | Map of bucket key → S3 bucket name |
| `codebuild_source_bucket` | S3 bucket for agent source code uploads. **Pass to `modules/agents` `codebuild_source_bucket` variable.** |
| `cloudfront_domain` | CloudFront distribution domain (empty when disabled) |
| `cloudfront_distribution_arn` | CloudFront distribution ARN |
| `artifact_queue_url` | SQS queue URL for artifact event notifications |

### AgentCore

| Output | Description |
|--------|-------------|
| `gateway_id` | AgentCore Gateway ID |
| `gateway_url` | AgentCore Gateway MCP endpoint URL |
| `gateway_arn` | AgentCore Gateway ARN |
| `gateway_role_arn` | IAM role ARN used by Gateway to invoke targets |
| `memory_id` | AgentCore Memory resource ID |
| `memory_arn` | AgentCore Memory resource ARN |
| `code_interpreter_id` | Built-in Code Interpreter tool ID (empty when disabled) |
| `browser_id` | Built-in Browser tool ID (empty when disabled) |
| `cognito_user_pool_id` | Cognito User Pool ID (empty when `cognito_enabled` is false) |
| `cognito_client_id` | Cognito App Client ID (empty when disabled) |
| `mcp_oauth2_provider_arn` | OAuth2 credential provider ARN for MCP Gateway auth |
| `mcp_oauth2_scopes` | OAuth2 scopes for MCP Gateway auth |
| `mcp_oauth2_discovery_url` | OIDC discovery URL for MCP Runtime JWT authorizer |
| `mcp_oauth2_allowed_clients` | Allowed client IDs for MCP Runtime JWT authorizer |
| `mcp_m2m_client_id` | Cognito M2M client ID (sensitive; AWS Issue #809 workaround) |
| `mcp_m2m_client_secret` | Cognito M2M client secret (sensitive) |
| `cognito_token_url` | Cognito token endpoint URL for M2M flows |

### Observability

| Output | Description |
|--------|-------------|
| `alert_topic_arn` | SNS alert topic ARN |
| `pipeline_log_group_name` | CloudWatch log group name for pipeline logs |

### API

| Output | Description |
|--------|-------------|
| `api_url` | Artifact store API Gateway URL |
| `artifacts_mcp_lambda_arn` | ARN of the artifacts MCP tools Lambda |
| `artifacts_mcp_lambda_name` | Name of the artifacts MCP tools Lambda |
| `lambda_layer_arn` | ARN of the shared platform Lambda layer |

### Prompt Registry

| Output | Description |
|--------|-------------|
| `prompt_registry_url` | Lambda Function URL for the Prompt Registry API |
| `prompt_registry_function_arn` | Prompt Registry Lambda ARN. **Pass to `modules/agents` to grant `lambda:InvokeFunction` to agent roles.** |
| `prompt_registry_function_name` | Prompt Registry Lambda function name |

---

## Usage Example

```hcl
module "platform" {
  source = "git::https://github.com/your-org/aws-agent-platform.git//modules/platform?ref=v1.0.0"

  # Identity
  environment     = var.environment
  resource_prefix = "myplatform"
  aws_region      = var.aws_region
  bedrock_region  = var.bedrock_region
  ssm_root_path   = "/myplatform/${var.environment}"

  # Networking — externally managed
  vpc_id              = var.vpc_id
  private_subnet_ids  = var.private_subnet_ids
  public_subnet_ids   = var.public_subnet_ids
  isolated_subnet_ids = var.isolated_subnet_ids

  # Security
  waf_enabled = var.environment != "dev"

  # AgentCore
  gateway_auth_type                = "AWS_IAM"
  memory_event_expiry_days         = 90
  cognito_enabled                  = true
  builtin_code_interpreter_enabled = true

  # Data
  removal_policy_destroy = var.environment == "dev"

  tags = {
    Project   = "my-agent-platform"
    ManagedBy = "Terraform"
  }
}
```

Pass platform outputs to downstream modules:

```hcl
module "agents" {
  source     = "git::https://github.com/your-org/aws-agent-platform.git//modules/agents?ref=v1.0.0"
  depends_on = [module.platform]

  # Core wiring
  gateway_id              = module.platform.gateway_id
  gateway_url             = module.platform.gateway_url
  gateway_role_arn        = module.platform.gateway_role_arn
  memory_id               = module.platform.memory_id
  vpc_id                  = module.platform.vpc_id
  private_subnet_ids      = module.platform.private_subnet_ids
  agent_security_group_id = module.platform.agent_security_group_id
  storage_kms_key_arn     = module.platform.storage_kms_key_arn
  codebuild_source_bucket = module.platform.codebuild_source_bucket

  # Prompt Registry
  prompt_registry_url          = module.platform.prompt_registry_url
  prompt_registry_function_arn = module.platform.prompt_registry_function_arn

  # MCP OAuth2 (conditional on cognito_enabled)
  mcp_oauth2_provider_arn    = module.platform.mcp_oauth2_provider_arn
  mcp_oauth2_scopes          = module.platform.mcp_oauth2_scopes
  mcp_oauth2_discovery_url   = module.platform.mcp_oauth2_discovery_url
  mcp_oauth2_allowed_clients = module.platform.mcp_oauth2_allowed_clients

  # Guardrail (conditional on guardrail_enabled)
  guardrail_id      = module.platform.guardrail_id
  guardrail_version = module.platform.guardrail_version

  # ...
}
```

---

## SSM Cross-Module Interface

Every platform output is also written as an SSM parameter under `${ssm_root_path}/`. This lets downstream teams and CI pipelines read platform values without Terraform state access:

```bash
aws ssm get-parameter \
  --name "/myplatform/dev/agentcore/gateway-url" \
  --query "Parameter.Value" --output text
```

See the [Deployment Patterns](./deployment-patterns) page for the full SSM path reference and a walkthrough of the complete deployment sequence.
