---
title: Platform Module
nav_order: 1
---

# Platform Module

The platform module (`modules/platform/`) provisions the shared infrastructure that all agents and workflows depend on. It is the first module deployed and emits outputs consumed by the agents and workflows modules.

The module is composed of six sub-modules that wire together automatically. Domain repos consume the platform module as a single unit — the internal sub-module boundaries are an implementation detail.

---

## Sub-Modules

| Sub-Module | Path | What It Provisions |
|------------|------|--------------------|
| **network** | `modules/platform/modules/network` | VPC, public/private/isolated subnets, NAT gateways, security groups for agent runtimes and MCP servers, VPC endpoint for `bedrock-agentcore` |
| **security** | `modules/platform/modules/security` | Five KMS keys (data, storage, secrets, platform\_artifacts, domain\_artifacts), WAF WebACL (conditional), network security group rules |
| **data** | `modules/platform/modules/data` | DynamoDB tables (sessions, artifacts, audit\_log, evaluation, policy\_versions), S3 buckets (platform artifacts, domain artifacts), SQS queue, CloudFront distribution (conditional) |
| **observability** | `modules/platform/modules/observability` | CloudWatch log groups, SNS alert topic, CloudWatch Alarms |
| **api** | `modules/platform/modules/api` | API Gateway HTTP API, Lambda function for artifact store (claim-check pattern), stage throttle settings |
| **agentcore** | `modules/platform/modules/agentcore` | AgentCore Gateway (with KMS encryption + Cedar policy engine), AgentCore Memory resource, Cognito user pool (conditional), built-in Code Interpreter (conditional), built-in Browser (conditional) |

All platform outputs are also written as SSM parameters under `${var.ssm_root_path}/` for cross-account and cross-module consumption without requiring Terraform state sharing.

---

## Input Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `environment` | `string` | — | Deployment environment: `dev`, `staging`, or `production` |
| `resource_prefix` | `string` | — | Prefix for all resource names (e.g. `platform`) |
| `aws_region` | `string` | — | Primary AWS region for deployment |
| `bedrock_region` | `string` | — | Region for Bedrock model access (may differ from primary) |
| `ssm_root_path` | `string` | — | Root SSM parameter path (e.g. `/platform/dev`) |
| `vpc_cidr` | `string` | `"10.0.0.0/16"` | VPC CIDR block |
| `availability_zones` | `list(string)` | `[]` | AZs to deploy subnets into. Auto-resolved if empty. |
| `nat_gateway_count` | `number` | `1` | Number of NAT gateways (1 for dev, 3 for production HA) |
| `kms_key_deletion_window_days` | `number` | `30` | KMS key deletion window |
| `waf_enabled` | `bool` | `false` | Enable WAF WebACL (attach to API Gateway and CloudFront) |
| `waf_rate_limit` | `number` | `1000` | WAF rate-limit rule threshold (requests per 5 minutes) |
| `waf_ip_whitelist` | `list(string)` | `[]` | IP CIDRs to allowlist in WAF |
| `dynamodb_billing_mode` | `string` | `"PAY_PER_REQUEST"` | `PAY_PER_REQUEST` or `PROVISIONED` |
| `dynamodb_read_capacity` | `number` | `25` | Read capacity units (PROVISIONED mode only) |
| `dynamodb_write_capacity` | `number` | `10` | Write capacity units (PROVISIONED mode only) |
| `cloudfront_enabled` | `bool` | `true` | Enable CloudFront distribution in front of S3 |
| `removal_policy_destroy` | `bool` | `true` | `true` for dev (destroy on removal), `false` for staging/production (retain) |
| `gateway_auth_type` | `string` | `"AWS_IAM"` | AgentCore Gateway inbound auth: `AWS_IAM`, `CUSTOM_JWT`, or `NONE` |
| `gateway_jwt_discovery_url` | `string` | `""` | OIDC discovery URL (CUSTOM\_JWT mode) |
| `gateway_jwt_allowed_clients` | `list(string)` | `[]` | Allowed JWT client IDs (CUSTOM\_JWT mode) |
| `memory_event_expiry_days` | `number` | `30` | AgentCore Memory event retention in days |
| `memory_description` | `string` | `""` | Description for the AgentCore Memory resource |
| `cognito_enabled` | `bool` | `false` | Provision Cognito User Pool and App Client |
| `builtin_browser_enabled` | `bool` | `false` | Provision AgentCore Browser built-in tool |
| `builtin_code_interpreter_enabled` | `bool` | `false` | Provision AgentCore Code Interpreter built-in tool |
| `log_retention_days` | `number` | `14` | CloudWatch log group retention |
| `sns_alert_email` | `string` | `""` | Email address for SNS alert subscriptions |
| `api_throttle_rate` | `number` | `100` | API Gateway throttle rate limit (requests/sec) |
| `api_throttle_burst` | `number` | `200` | API Gateway throttle burst limit |
| `api_cors_origins` | `list(string)` | `[]` | Allowed CORS origins for the artifact API |
| `tags` | `map(string)` | `{}` | Additional resource tags merged with platform defaults |

---

## Outputs

### Network

| Output | Description |
|--------|-------------|
| `vpc_id` | VPC ID |
| `vpc_cidr_block` | VPC CIDR block |
| `public_subnet_ids` | List of public subnet IDs |
| `private_subnet_ids` | List of private subnet IDs |
| `isolated_subnet_ids` | List of isolated subnet IDs (no internet access) |
| `agent_security_group_id` | Security group ID for agent runtime containers |
| `mcp_security_group_id` | Security group ID for MCP server containers |

### Security

| Output | Description |
|--------|-------------|
| `platform_artifacts_kms_key_arn` | KMS key ARN for platform artifact encryption |
| `domain_artifacts_kms_key_arn` | KMS key ARN for domain artifact encryption |
| `data_kms_key_arn` | KMS key ARN for DynamoDB and AgentCore resources |
| `storage_kms_key_arn` | KMS key ARN for S3 and ECR encryption |
| `waf_acl_arn` | WAF WebACL ARN (empty string when WAF is disabled) |

### Data

| Output | Description |
|--------|-------------|
| `table_names` | Map of table key → DynamoDB table name |
| `table_arns` | Map of table key → DynamoDB table ARN |
| `artifacts_bucket_name` | Artifacts S3 bucket name |
| `artifacts_bucket_arn` | Artifacts S3 bucket ARN |
| `bucket_names` | Map of bucket key → S3 bucket name |
| `cloudfront_domain` | CloudFront distribution domain (empty when disabled) |
| `cloudfront_distribution_arn` | CloudFront distribution ARN |
| `artifact_queue_url` | SQS queue URL for artifact event notifications |

### AgentCore

| Output | Description |
|--------|-------------|
| `gateway_id` | AgentCore Gateway ID |
| `gateway_url` | AgentCore Gateway URL for agent tool access |
| `gateway_arn` | AgentCore Gateway ARN |
| `gateway_role_arn` | IAM role ARN used by Gateway to invoke targets |
| `memory_id` | AgentCore Memory resource ID |
| `memory_arn` | AgentCore Memory resource ARN |
| `code_interpreter_id` | Built-in Code Interpreter tool ID (empty when disabled) |
| `browser_id` | Built-in Browser tool ID (empty when disabled) |
| `cognito_user_pool_id` | Cognito User Pool ID (empty when disabled) |
| `cognito_client_id` | Cognito App Client ID (empty when disabled) |

### Observability

| Output | Description |
|--------|-------------|
| `alert_topic_arn` | SNS alert topic ARN |
| `pipeline_log_group_name` | CloudWatch log group name for pipeline logs |

### API

| Output | Description |
|--------|-------------|
| `api_url` | Artifact store API Gateway URL |

---

## Usage Example

```hcl
module "platform" {
  source = "git::https://github.com/your-org/aws-agent-platform.git//modules/platform?ref=v1.0.0"

  environment     = var.environment
  resource_prefix = "myplatform"
  aws_region      = var.aws_region
  bedrock_region  = "${AWS_BEDROCK_REGION}"
  ssm_root_path   = "/myplatform/${var.environment}"

  # Network
  vpc_cidr          = "10.10.0.0/16"
  availability_zones = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  nat_gateway_count  = var.environment == "production" ? 3 : 1

  # Security
  waf_enabled = var.environment != "dev"

  # AgentCore
  gateway_auth_type                = "AWS_IAM"
  memory_event_expiry_days         = 90
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
  source = "git::https://github.com/your-org/aws-agent-platform.git//modules/agents?ref=v1.0.0"

  gateway_id              = module.platform.gateway_id
  gateway_url             = module.platform.gateway_url
  gateway_role_arn        = module.platform.gateway_role_arn
  memory_id               = module.platform.memory_id
  vpc_id                  = module.platform.vpc_id
  private_subnet_ids      = module.platform.private_subnet_ids
  agent_security_group_id = module.platform.agent_security_group_id
  storage_kms_key_arn     = module.platform.storage_kms_key_arn
  # ...
}
```
