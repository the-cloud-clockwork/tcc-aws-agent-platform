# Infrastructure Audit — Terraform Modules

> Full audit of `modules/` Terraform infrastructure against the AWS provider schema,
> CloudFormation resource definitions, project vision, and cross-module wiring.
>
> **Date:** 2026-03-21
> **Provider:** hashicorp/aws >= 6.21
> **AWS Service:** Amazon Bedrock AgentCore

---

## Severity Legend

| Level | Meaning |
|-------|---------|
| **CRITICAL** | Will cause `terraform plan` or `apply` to fail |
| **HIGH** | Missing functionality, incorrect behavior, or security gap |
| **MEDIUM** | Best practice violation, completeness gap, or future risk |
| **LOW** | Minor improvement or cosmetic issue |

---

## 1. CRITICAL: Sub-Module Interface Mismatches

The root `platform/main.tf` and `platform/outputs.tf` were written for production-grade sub-modules, but the actual `data/`, `security/`, `network/`, `observability/`, and `api/` sub-modules are **stubs with incompatible interfaces**. The `agentcore/` sub-module is fully implemented and correct.

### 1.1 security/ Module

**Root passes (main.tf:21-32):**
```
resource_prefix, environment, kms_key_deletion_window_days,
waf_enabled, waf_rate_limit, waf_ip_whitelist,
vpc_id, vpc_cidr_block, private_subnet_ids, tags
```

**Sub-module variables.tf accepts:**
```
environment, aws_region, vpc_id, vpc_cidr,
route_table_ids, private_subnet_ids, tags
```

| Variable | Root Passes | Sub-Module Expects | Status |
|----------|-------------|-------------------|--------|
| `resource_prefix` | Yes | No | MISSING in sub-module |
| `kms_key_deletion_window_days` | Yes | No | MISSING in sub-module |
| `waf_enabled` | Yes | No | MISSING — WAF always created |
| `waf_rate_limit` | Yes | No | MISSING — hardcoded 2000 |
| `waf_ip_whitelist` | Yes | No | MISSING — no whitelist support |
| `vpc_cidr_block` | Yes (from network output) | Expects `vpc_cidr` | NAME MISMATCH |
| `aws_region` | No | Yes | MISSING in root call |
| `route_table_ids` | No | Yes | MISSING in root call |

**Root outputs.tf references these security outputs:**
- `module.security.data_kms_key_arn` — DOES NOT EXIST (sub-module outputs `kms_key_arn`)
- `module.security.storage_kms_key_arn` — DOES NOT EXIST
- `module.security.platform_artifacts_kms_key_arn` — DOES NOT EXIST
- `module.security.domain_artifacts_kms_key_arn` — DOES NOT EXIST
- `module.security.waf_acl_arn` — EXISTS (matches)

**Sub-module creates 1 KMS key. Root expects 5 separate keys** (data, storage, secrets, platform_artifacts, domain_artifacts).

---

### 1.2 data/ Module

**Root passes (main.tf:34-49):**
```
resource_prefix, environment, account_id,
data_kms_key_arn, storage_kms_key_arn,
platform_artifacts_kms_key_arn, domain_artifacts_kms_key_arn,
dynamodb_billing_mode, dynamodb_read_capacity, dynamodb_write_capacity,
cloudfront_enabled, waf_acl_arn, removal_policy_destroy, tags
```

**Sub-module variables.tf accepts:**
```
environment, log_retention_days, tags
```

| Variable | Root Passes | Sub-Module Expects | Status |
|----------|-------------|-------------------|--------|
| `resource_prefix` | Yes | No | MISSING |
| `account_id` | Yes | No | MISSING |
| `data_kms_key_arn` | Yes | No | MISSING |
| `storage_kms_key_arn` | Yes | No | MISSING |
| `platform_artifacts_kms_key_arn` | Yes | No | MISSING |
| `domain_artifacts_kms_key_arn` | Yes | No | MISSING |
| `dynamodb_billing_mode` | Yes | No | MISSING |
| `dynamodb_read_capacity` | Yes | No | MISSING |
| `dynamodb_write_capacity` | Yes | No | MISSING |
| `cloudfront_enabled` | Yes | No | MISSING — always created |
| `waf_acl_arn` | Yes | No | MISSING |
| `removal_policy_destroy` | Yes | No | MISSING |
| `log_retention_days` | No | Yes | MISSING in root call |

**Root outputs.tf references these data outputs:**
- `module.data.table_names` — DOES NOT EXIST
- `module.data.table_arns` — DOES NOT EXIST
- `module.data.artifacts_bucket_name` — EXISTS (matches)
- `module.data.artifacts_bucket_arn` — DOES NOT EXIST
- `module.data.bucket_names` — DOES NOT EXIST
- `module.data.cloudfront_domain` — DOES NOT EXIST (sub-module outputs `cloudfront_domain_name`)
- `module.data.cloudfront_distribution_arn` — DOES NOT EXIST
- `module.data.artifact_queue_url` — DOES NOT EXIST

**Sub-module is missing:**
- 5 DynamoDB tables (artifacts, audit_log, prompt_registry, run_history, idempotency)
- 2 additional S3 buckets (prompt_registry, historical_data)
- SQS queues (artifact_notifications + DLQ)
- Two-tier KMS enforcement on artifacts bucket
- Lifecycle policies per bucket
- Conditional CloudFront with OAC

---

### 1.3 network/ Module

**Root passes (main.tf:10-18):**
```
resource_prefix, environment, vpc_cidr,
availability_zones (list(string)), nat_gateway_count, tags
```

**Sub-module variables.tf accepts:**
```
environment, vpc_cidr, public_subnet_cidrs (list(string)),
private_subnet_cidrs (list(string)),
availability_zones (number), tags
```

| Variable | Root Passes | Sub-Module Expects | Status |
|----------|-------------|-------------------|--------|
| `resource_prefix` | Yes | No | MISSING |
| `availability_zones` | list(string) | number | TYPE MISMATCH |
| `nat_gateway_count` | Yes | No | MISSING — creates 1 NAT per AZ always |
| `public_subnet_cidrs` | No | Yes (with defaults) | MISSING in root call |
| `private_subnet_cidrs` | No | Yes (with defaults) | MISSING in root call |

**Root outputs.tf references:**
- `module.network.vpc_cidr_block` — DOES NOT EXIST (sub-module outputs `vpc_cidr`)
- `module.network.isolated_subnet_ids` — DOES NOT EXIST (sub-module has no isolated subnets)
- `module.network.agent_security_group_id` — DOES NOT EXIST
- `module.network.mcp_security_group_id` — DOES NOT EXIST

**Sub-module is missing:**
- 3-tier subnet architecture (public/private/isolated)
- Configurable NAT gateway count
- Agent security group (all outbound, no inbound)
- MCP security group (inbound TCP 8080 from agents)
- CIDR auto-allocation from VPC CIDR

---

### 1.4 observability/ Module

**Root passes (main.tf:63-72):**
```
resource_prefix, environment, log_retention_days,
sns_alert_email, kms_key_arn, tags
```

**Sub-module variables.tf accepts:**
```
environment, log_retention_days,
langfuse_api_url, langfuse_public_key, langfuse_secret_key, tags
```

| Variable | Root Passes | Sub-Module Expects | Status |
|----------|-------------|-------------------|--------|
| `resource_prefix` | Yes | No | MISSING |
| `sns_alert_email` | Yes | No | MISSING |
| `kms_key_arn` | Yes | No | MISSING |
| `langfuse_api_url` | No | Yes | MISSING in root call |
| `langfuse_public_key` | No | Yes (sensitive) | MISSING in root call |
| `langfuse_secret_key` | No | Yes (sensitive) | MISSING in root call |

**Root outputs.tf references:**
- `module.observability.alert_topic_arn` — DOES NOT EXIST
- `module.observability.pipeline_log_group_name` — DOES NOT EXIST

**Sub-module is missing:**
- SNS alert topic with optional email subscription
- Pipeline log group (/{prefix}/{env}/pipeline)
- CloudWatch dashboard (Agent Invocations, Token Cost, Pipeline Executions)
- X-Ray group with environment filter

**Sub-module has extras not wired from root:**
- Langfuse credentials as variables (should be in Secrets Manager, not TF variables)

---

### 1.5 api/ Module

**Root passes (main.tf:74-88):**
```
resource_prefix, environment, artifacts_table_name, artifacts_table_arn,
artifacts_bucket_name, artifacts_bucket_arn,
platform_artifacts_kms_key_arn, domain_artifacts_kms_key_arn,
api_throttle_rate, api_throttle_burst, api_cors_origins,
waf_acl_arn, waf_enabled, tags
```

**Sub-module variables.tf accepts:**
```
environment, lambda_function_arn, cors_allowed_origins,
api_authorization_type, api_authorizer_id, log_retention_days, tags
```

| Variable | Root Passes | Sub-Module Expects | Status |
|----------|-------------|-------------------|--------|
| `resource_prefix` | Yes | No | MISSING |
| `artifacts_table_name` | Yes | No | MISSING |
| `artifacts_table_arn` | Yes | No | MISSING |
| `artifacts_bucket_name` | Yes | No | MISSING |
| `artifacts_bucket_arn` | Yes | No | MISSING |
| `platform_artifacts_kms_key_arn` | Yes | No | MISSING |
| `domain_artifacts_kms_key_arn` | Yes | No | MISSING |
| `api_throttle_rate` | Yes | No | MISSING |
| `api_throttle_burst` | Yes | No | MISSING |
| `api_cors_origins` | Yes | Expects `cors_allowed_origins` | NAME MISMATCH |
| `waf_acl_arn` | Yes | No | MISSING |
| `waf_enabled` | Yes | No | MISSING |
| `lambda_function_arn` | No | Yes (required!) | MISSING in root — root should create Lambda |
| `api_authorization_type` | No | Yes | MISSING in root call |
| `api_authorizer_id` | No | Yes | MISSING in root call |
| `log_retention_days` | No | Yes | MISSING in root call |

**Root outputs.tf references:**
- `module.api.api_url` — DOES NOT EXIST (sub-module outputs `api_endpoint`)

**Sub-module is missing:**
- Lambda function creation (artifacts-api)
- REST API Gateway (uses HTTP API instead)
- IAM role for Lambda execution
- Specific routes (GET /api/artifacts, /artifacts/{id}, /runs, etc.)
- AWS_IAM authorization on routes
- Throttling configuration
- WAF association

---

## 2. CRITICAL: Provider Resource Schema Issues

### 2.1 Runtime `protocol_configuration` — Block vs String

**Our code (`agents/runtime.tf`):**
```hcl
protocol_configuration {
  protocol = try(each.value.runtime.protocol, "HTTP")
}
```

**CloudFormation schema says `ProtocolConfiguration` is a String:**
```
ProtocolConfiguration: String
Allowed values: MCP | HTTP | A2A
```

If the Terraform provider maps this as a simple string attribute (not a nested block), this will fail. The provider may wrap it differently — **verify against provider source or `terraform validate`**.

---

### 2.2 Memory `event_expiry_duration` — Minimum Value

**Our code (`agentcore/variables.tf`):**
```hcl
validation {
  condition     = var.memory_event_expiry_days >= 1
  error_message = "memory_event_expiry_days must be at least 1."
}
```

**CloudFormation schema says:** `EventExpiryDuration: Integer, Range: 3-365`

The API will reject values 1 or 2. Validation should enforce `>= 3`.

---

### 2.3 Gateway Target `credential_provider_configurations` — Structure

**Our code (`agents/gateway_targets.tf`):**
```hcl
credential_provider_configurations = [
  {
    credential_provider_type = "GATEWAY_IAM_ROLE"
  }
]
```

This is written as an attribute assignment with a list of objects. In the Terraform AWS provider, this is likely a **nested block**, not an attribute. Should be:
```hcl
credential_provider_configurations {
  credential_provider_type = "GATEWAY_IAM_ROLE"
}
```

---

### 2.4 Gateway Target `tool_schema` — Inline Payload Structure

**Our code:**
```hcl
tool_schema {
  inline_payload {
    inline_tool_definitions = [...]
  }
}
```

The actual provider schema for tool_schema may use different nesting. The CloudFormation ToolSchema type has `InlinePayload` with `InlineToolDefinitions` — but the Terraform provider attribute names may differ. **Verify against provider source.**

---

## 3. HIGH: Missing Infrastructure Resources

### 3.1 No Backend Configuration

No `backend.tf` file exists in any module. State is stored locally by default. Production deployments MUST use remote state (S3 + DynamoDB locking).

**Needed:**
```hcl
terraform {
  backend "s3" {
    bucket         = "platform-terraform-state-{account_id}"
    key            = "platform/{environment}/terraform.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "terraform-state-lock"
    encrypt        = true
  }
}
```

---

### 3.2 No Cross-Region Provider for Bedrock

`bedrock_region` (us-west-2) differs from `aws_region` (eu-west-1), but no aliased provider exists for cross-region operations. If any Terraform resource needs to create Bedrock resources in us-west-2, it will fail.

**Needed in `providers.tf`:**
```hcl
provider "aws" {
  alias  = "bedrock"
  region = var.bedrock_region
  # ... same default_tags
}
```

---

### 3.3 Missing `aws_bedrockagentcore_runtime_endpoint` Resource

The AWS provider issue #43424 lists `aws_bedrockagentcore_runtime_endpoint` as a separate resource from `aws_bedrockagentcore_agent_runtime`. Our `agents/runtime.tf` only creates the runtime but NOT the endpoint. Without an endpoint, the runtime may not be reachable.

---

### 3.4 Missing Gateway KMS Encryption

CloudFormation schema shows `KmsKeyArn` as an optional property on `AWS::BedrockAgentCore::Gateway`. Our `agentcore/gateway.tf` does not set this. Gateway data should be encrypted with a customer-managed KMS key.

---

### 3.5 Missing Gateway `PolicyEngineConfiguration`

CloudFormation shows `PolicyEngineConfiguration` on the Gateway resource. This is where Block 8 (Policy/Cedar) would connect at the infrastructure level. Without this, Cedar policies deployed via SDK have no infrastructure backing in Terraform.

---

### 3.6 Missing Gateway `InterceptorConfigurations`

CloudFormation shows `InterceptorConfigurations` (array, max 2 items) for Lambda interceptors. This enables pre/post-processing of Gateway requests. Not implemented.

---

### 3.7 Missing Runtime `LifecycleConfiguration`

CloudFormation shows `LifecycleConfiguration` with `MaxLifetime` and `IdleRuntimeSessionTimeout`. Without this, runtimes use AWS defaults which may not match operational requirements.

---

### 3.8 Missing Runtime `AuthorizerConfiguration`

CloudFormation shows `AuthorizerConfiguration` on the Runtime resource. This allows per-runtime authorization (separate from Gateway-level auth). Not implemented.

---

### 3.9 Missing Runtime `RequestHeaderConfiguration`

CloudFormation shows `RequestHeaderConfiguration` for HTTP request headers passed to the runtime. Not implemented.

---

### 3.10 Missing Memory `StreamDeliveryResources`

CloudFormation shows `StreamDeliveryResources` on Memory. This enables streaming memory events to external systems (e.g., Kinesis). Not implemented.

---

### 3.11 Missing `aws_bedrockagentcore_workload_provider` Resource

Listed in provider issue #43424 but not created anywhere. Workload providers enable non-agent workloads to access AgentCore resources.

---

### 3.12 Missing `aws_bedrockagentcore_oauth2_credential_provider` Resource

Listed in provider issue #43424. Our `identity_providers.tf` explicitly skips OAuth2 providers with a comment about secrets. However, the Terraform resource exists and can be used with `sensitive` attributes or Secrets Manager references, avoiding plaintext secrets in state.

---

## 4. HIGH: Security Issues

### 4.1 ECR Encryption Uses AES256, Not KMS

**`agents/ecr.tf`:**
```hcl
encryption_configuration {
  encryption_type = "AES256"
}
```

Should use KMS encryption with the platform's storage key for consistency with the two-tier encryption strategy.

---

### 4.2 CloudFront Uses Legacy OAI

**`data/cloudfront.tf`** uses `aws_cloudfront_origin_access_identity` (legacy). AWS recommends Origin Access Control (OAC) with SigV4 signing. OAI is deprecated for new distributions.

---

### 4.3 Observability Module Accepts Langfuse Secrets as Variables

**`observability/variables.tf`:**
```hcl
variable "langfuse_public_key" {
  sensitive = true
}
variable "langfuse_secret_key" {
  sensitive = true
}
```

Secrets should be in AWS Secrets Manager (already created in the security module's `observability_api_key` secret), not passed as Terraform variables where they end up in state.

---

### 4.4 Agent IAM Roles Use Wildcard Resources

**`agents/iam.tf`** uses `resources = ["*"]` for:
- `bedrock:InvokeModel` — Should scope to specific model ARNs from blueprint
- `ecr:GetAuthorizationToken` — Must be `*` (API requirement), OK
- `logs:*` — Should scope to agent-specific log groups
- `xray:*` — Must be `*` (API requirement), OK

---

### 4.5 WAF Rate Limit Hardcoded at 2000

**`security/waf.tf`** hardcodes `limit = 2000` instead of using a variable. The root module passes `waf_rate_limit` but the sub-module ignores it.

---

## 5. MEDIUM: Step Functions Integration

### 5.1 Agent Invocation Resource ARN

**`workflows/state_machines.tf`:**
```hcl
Resource = "arn:aws:states:::bedrock-agentcore:invokeAgentRuntime"
```

This is the Step Functions optimized integration pattern. Verify that:
1. This exact service integration exists in Step Functions
2. The `AgentRuntimeArn` parameter name is correct
3. The `SessionState.Prompt.$` JSONPath reference is correct

The actual Step Functions integration for AgentCore may use a different resource ARN format or parameter structure.

---

### 5.2 SFN Role Missing States:StartExecution for Nested Workflows

If workflows invoke other workflows (e.g., parallel orchestration), the SFN role needs `states:StartExecution` permission. Currently not included.

---

## 6. MEDIUM: Configuration and Best Practices

### 6.1 No Provider Version Constraints in Sub-Modules

Sub-modules (`data/`, `security/`, `network/`, `observability/`, `api/`) use `required_version = ">= 1.4"` while the root and `agents/`/`workflows/` modules use `>= 1.10`. These should be consistent.

---

### 6.2 Network Module Creates NAT Per AZ Always

`network/main.tf` creates `length(local.azs)` NAT gateways regardless of cost optimization needs. The root passes `nat_gateway_count` but the sub-module doesn't accept it. Dev should use 1 NAT, production should use N (matching AZ count).

---

### 6.3 No DynamoDB Table GSIs

The platform expects DynamoDB tables for artifacts, audit_log, etc. These tables likely need Global Secondary Indexes for query patterns:
- artifacts: by `agent_id`, by `run_id`
- audit_log: by `agent_id`, by `event_type`
- run_history: by `agent_id`, by `status`

---

### 6.4 No S3 Bucket Notification for Artifact Events

The root expects `module.data.artifact_queue_url` (SQS queue) for artifact event notifications. The data sub-module has no SQS resources and no S3 bucket notification configuration.

---

### 6.5 Missing SSM Parameters for Sub-Module Outputs

The platform `outputs.tf` creates SSM parameters for all major resource IDs/ARNs. But since the sub-module outputs don't exist, none of these SSM parameters can be created.

---

### 6.6 CodeBuild Uses `NO_SOURCE`

**`agents/codebuild.tf`:**
```hcl
source {
  type = "NO_SOURCE"
}
```

With `NO_SOURCE`, CodeBuild has no source to build from. The buildspec runs `docker build .` but there's no source code in the build environment. Either:
- Use `S3` source type with the `codebuild_source_bucket` variable
- Use `GITHUB` source type with webhook
- Use `CODECOMMIT` source type

---

### 6.7 Memory Strategy Type Mapping May Be Incorrect

**`agents/memory_strategies.tf`:**
```hcl
strategy_type_map = {
  "SUMMARY"         = "SUMMARIZATION"
  "SUMMARIZATION"   = "SUMMARIZATION"
  "SEMANTIC"        = "SEMANTIC"
  "USER_PREFERENCE" = "USER_PREFERENCE"
}
```

CloudFormation shows strategy types as `ShortTermMemory` in the example. The actual allowed values may be different from what we're using. **Verify against the MemoryStrategy property type documentation.**

---

### 6.8 No Terraform State Locking

Without a DynamoDB table for state locking, concurrent `terraform apply` operations can corrupt state. This is required for any team-based workflow.

---

## 7. LOW: Minor Issues

### 7.1 Inconsistent Tagging

- Sub-modules add their own `Module` tag but use different patterns
- Root `locals.tf` merges tags with hardcoded values that duplicate `providers.tf` default_tags
- Some resources have `Name` tags, others don't

### 7.2 No Resource Import Blocks

For brownfield deployments where resources already exist, `import` blocks would allow adopting existing infrastructure without recreation.

### 7.3 No `moved` Blocks for Refactoring

When sub-modules are rewritten to match the root interface, `moved` blocks will be needed to prevent Terraform from destroying and recreating resources.

### 7.4 Agents Module Missing `depends_on` for Platform Resources

The agents module references platform outputs (gateway_url, memory_id) but has no explicit dependency. When composed in a root module, `depends_on` or data source lookups may be needed.

---

## 8. Summary — Action Items by Priority

### Must Fix (Terraform will not work without these)

| # | Finding | Section | Files |
|---|---------|---------|-------|
| 1 | Rewrite `security/` sub-module to match root interface (5 KMS keys, conditional WAF, correct variable names) | 1.1 | `modules/platform/modules/security/*` |
| 2 | Rewrite `data/` sub-module to match root interface (5 DynamoDB tables, 3 S3 buckets, SQS, conditional CloudFront with OAC) | 1.2 | `modules/platform/modules/data/*` |
| 3 | Rewrite `network/` sub-module to match root interface (3-tier subnets, configurable NAT, security groups) | 1.3 | `modules/platform/modules/network/*` |
| 4 | Rewrite `observability/` sub-module to match root interface (SNS, dashboard, X-Ray group, pipeline log group) | 1.4 | `modules/platform/modules/observability/*` |
| 5 | Rewrite `api/` sub-module to match root interface (Lambda creation, REST API, specific routes, throttling, WAF) | 1.5 | `modules/platform/modules/api/*` |
| 6 | Fix Runtime `protocol_configuration` — verify block vs string against provider | 2.1 | `modules/agents/runtime.tf` |
| 7 | Fix Memory `event_expiry_duration` minimum validation (3, not 1) | 2.2 | `modules/platform/modules/agentcore/variables.tf` |
| 8 | Fix Gateway target `credential_provider_configurations` — block vs attribute | 2.3 | `modules/agents/gateway_targets.tf` |

### Should Fix (Missing functionality)

| # | Finding | Section | Files |
|---|---------|---------|-------|
| 9 | Add backend configuration for remote state | 3.1 | New `backend.tf` |
| 10 | Add cross-region provider alias for Bedrock | 3.2 | `modules/platform/providers.tf` |
| 11 | Add `aws_bedrockagentcore_runtime_endpoint` | 3.3 | `modules/agents/runtime.tf` |
| 12 | Add Gateway `kms_key_arn` for encryption | 3.4 | `modules/platform/modules/agentcore/gateway.tf` |
| 13 | Add Gateway `policy_engine_configuration` | 3.5 | `modules/platform/modules/agentcore/gateway.tf` |
| 14 | Add Runtime `lifecycle_configuration` | 3.7 | `modules/agents/runtime.tf` |
| 15 | Fix ECR to use KMS encryption | 4.1 | `modules/agents/ecr.tf` |
| 16 | Remove Langfuse secrets from TF variables | 4.3 | `modules/platform/modules/observability/variables.tf` |
| 17 | Scope agent IAM Bedrock permissions to model ARNs | 4.4 | `modules/agents/iam.tf` |
| 18 | Fix CodeBuild source type | 6.6 | `modules/agents/codebuild.tf` |

### Nice to Have

| # | Finding | Section | Files |
|---|---------|---------|-------|
| 19 | Verify Step Functions AgentCore integration ARN | 5.1 | `modules/workflows/state_machines.tf` |
| 20 | Add Gateway interceptor configurations | 3.6 | `modules/platform/modules/agentcore/gateway.tf` |
| 21 | Add Memory stream delivery resources | 3.10 | `modules/platform/modules/agentcore/memory.tf` |
| 22 | Add Runtime authorizer/request header config | 3.8, 3.9 | `modules/agents/runtime.tf` |
| 23 | Add DynamoDB GSIs for query patterns | 6.3 | `modules/platform/modules/data/main.tf` |
| 24 | Verify memory strategy type values | 6.7 | `modules/agents/memory_strategies.tf` |
| 25 | Consistent Terraform version constraints | 6.1 | All sub-module `versions.tf` |

---

## 9. References

- [AWS::BedrockAgentCore::Gateway CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrockagentcore-gateway.html)
- [AWS::BedrockAgentCore::Runtime CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrockagentcore-runtime.html)
- [AWS::BedrockAgentCore::Memory CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrockagentcore-memory.html)
- [Terraform AWS Provider — AgentCore Support Issue #43424](https://github.com/hashicorp/terraform-provider-aws/issues/43424)
- [Terraform AWS Provider — Runtime lifecycle_configuration Bug #45290](https://github.com/hashicorp/terraform-provider-aws/issues/45290)
- [Terraform AWS Provider — Gateway Target missing grant_type #46128](https://github.com/hashicorp/terraform-provider-aws/issues/46128)
- [Terraform AWS Provider — Gateway Target MCP server support #44976](https://github.com/hashicorp/terraform-provider-aws/issues/44976)
- [Deploy AI Agents with Terraform — AWS Bedrock AgentCore Guide](https://www.pierreange.ai/blog/deploy-ai-agents-aws-bedrock-agentcore-terraform)
