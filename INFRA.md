# Infrastructure Audit — Terraform Modules

> Full audit of `modules/` Terraform infrastructure against the AWS provider schema,
> CloudFormation resource definitions, project vision, and cross-module wiring.
>
> **Date:** 2026-03-21
> **Provider:** hashicorp/aws >= 6.21
> **AWS Service:** Amazon Bedrock AgentCore

>
> **Block 1 Status:** COMPLETE (2026-03-21). All 5 critical findings fixed. Additional schema mismatches
> discovered during `terraform validate` also fixed (see Block 1 completion notes below).
---

## Severity Legend

| Level | Meaning |
|-------|---------|
| **CRITICAL** | Will cause `terraform plan` or `apply` to fail |
| **HIGH** | Missing functionality, incorrect behavior, or security gap |
| **MEDIUM** | Best practice violation, completeness gap, or future risk |
| **LOW** | Minor improvement or cosmetic issue |

---

## Module Inventory — Verified Correct

All 6 platform sub-modules are fully implemented with correct variable/output interfaces matching the root composition:

| Sub-Module | Lines | Resources | Status |
|------------|-------|-----------|--------|
| `security/` | 506 | 17 | 5 KMS keys, conditional WAF, 12 VPC endpoints, Secrets Manager |
| `data/` | 754 | 21 | 5 DynamoDB tables, 3 S3 buckets (two-tier KMS), SQS + DLQ, conditional CloudFront with OAC |
| `network/` | 373 | 20 | 3-tier VPC (public/private/isolated), configurable NAT count, agent + MCP security groups |
| `observability/` | 199 | 5 | Pipeline log group, SNS alerts, X-Ray group, CloudWatch dashboard |
| `api/` | 758 | 46 | Lambda (ARM64), REST API Gateway, 5 GET routes with AWS_IAM, CORS, throttling, conditional WAF |
| `agentcore/` | ~300 | 10 | Gateway (MCP), Memory, conditional Cognito, conditional Code Interpreter + Browser |

| Deployment Module | Lines | Resources | Status |
|-------------------|-------|-----------|--------|
| `agents/` | ~700 | 30+ | Per-agent: IAM, ECR, CodeBuild, AgentCore Runtime, Gateway targets, Memory strategies, Identity providers, SSM |
| `workflows/` | ~400 | 10+ | Per-workflow: Step Functions, EventBridge triggers, IAM roles |

---

## 1. CRITICAL: Missing Lambda Placeholder File

**File:** `modules/platform/modules/api/main.tf:131`

```hcl
filename = "${path.module}/placeholder.zip"
```

The Lambda function references `placeholder.zip` but the file **does not exist** at `modules/platform/modules/api/placeholder.zip`. Terraform will fail with `file not found` during `plan`.

**Fix:** Create an empty zip placeholder:
```bash
cd modules/platform/modules/api && echo "" | zip placeholder.zip -
```

---

## 2. CRITICAL: Provider Resource Schema Risks

These are based on cross-referencing our HCL against the CloudFormation resource schemas. The Terraform AWS provider may map attributes differently, so each needs verification via `terraform validate` against the actual provider version.

### 2.1 Runtime `protocol_configuration` — Block vs String

**File:** `modules/agents/runtime.tf`

```hcl
protocol_configuration {
  protocol = try(each.value.runtime.protocol, "HTTP")
}
```

**CloudFormation schema** defines `ProtocolConfiguration` as a **String** with allowed values `MCP | HTTP | A2A` — not a nested object. If the Terraform provider maps this as a simple string attribute rather than a block, this will fail.

**Verify:** Run `terraform validate` or check provider source for `aws_bedrockagentcore_agent_runtime`.

---

### 2.2 Memory `event_expiry_duration` — Minimum Value Wrong

**File:** `modules/platform/modules/agentcore/variables.tf`

```hcl
validation {
  condition     = var.memory_event_expiry_days >= 1
  error_message = "memory_event_expiry_days must be at least 1."
}
```

**CloudFormation schema:** `EventExpiryDuration: Integer, Range: 3-365`

The API will reject values 1 or 2. Validation should enforce `>= 3`.

---

### 2.3 Gateway Target `credential_provider_configurations` — Attribute vs Block

**File:** `modules/agents/gateway_targets.tf`

```hcl
credential_provider_configurations = [
  {
    credential_provider_type = "GATEWAY_IAM_ROLE"
  }
]
```

Written as an attribute assignment with a list literal. In the Terraform AWS provider, nested structures are typically **blocks**, not attribute assignments:

```hcl
credential_provider_configurations {
  credential_provider_type = "GATEWAY_IAM_ROLE"
}
```

**Verify:** Run `terraform validate` or check provider schema.

---

### 2.4 Gateway Target `tool_schema` / `inline_payload` — Nesting Structure

**File:** `modules/agents/gateway_targets.tf`

```hcl
tool_schema {
  inline_payload {
    inline_tool_definitions = [...]
  }
}
```

The attribute `inline_tool_definitions` takes a list of objects with `input_schema` as a `jsonencode()`'d string. The actual provider may expect different attribute names or nesting. Additionally, GitHub issue [#44976](https://github.com/hashicorp/terraform-provider-aws/issues/44976) reports that `aws_bedrockagentcore_gateway_target` should support `mcp.mcp_server` target configuration, suggesting the API surface is still evolving.

---

## 3. HIGH: Missing AgentCore Resources

### 3.1 Missing `aws_bedrockagentcore_runtime_endpoint`

**Context:** AWS provider issue [#43424](https://github.com/hashicorp/terraform-provider-aws/issues/43424) lists `aws_bedrockagentcore_runtime_endpoint` as a separate resource (merged via PR #44301). Our `agents/runtime.tf` creates the runtime but not its endpoint. Without an endpoint, the runtime container may not be network-reachable.

**File:** `modules/agents/runtime.tf` — needs an additional resource block.

---

### 3.2 Missing Gateway `kms_key_arn`

**File:** `modules/platform/modules/agentcore/gateway.tf`

CloudFormation schema for `AWS::BedrockAgentCore::Gateway` includes an optional `KmsKeyArn` property. Our gateway resource does not set it. For consistency with the platform's envelope-encryption strategy (5 dedicated KMS keys), the gateway should use a customer-managed key.

---

### 3.3 Missing Gateway `policy_engine_configuration`

**File:** `modules/platform/modules/agentcore/gateway.tf`

CloudFormation shows `PolicyEngineConfiguration` on the Gateway resource. Block 8 (Policy/Cedar) in the Python SDK creates Cedar policies and a PolicyClient, but there is no corresponding Terraform resource to wire the policy engine to the Gateway infrastructure. This means policies created via SDK have no infrastructure-level backing.

---

### 3.4 Missing Runtime `lifecycle_configuration`

**File:** `modules/agents/runtime.tf`

CloudFormation shows `LifecycleConfiguration` with:
- `MaxLifetime` — Maximum runtime session lifetime
- `IdleRuntimeSessionTimeout` — Idle timeout before session teardown

Without this, runtimes use AWS defaults. Known bug: [#45290](https://github.com/hashicorp/terraform-provider-aws/issues/45290) — `lifecycle_configuration` attributes should be marked as `Computed` when not specified. This means even setting it may cause drift on subsequent applies.

**Recommendation:** Add with `lifecycle { ignore_changes = [lifecycle_configuration] }` until provider bug is fixed.

---

### 3.5 Missing `aws_bedrockagentcore_oauth2_credential_provider`

**File:** `modules/agents/identity_providers.tf`

Currently only `aws_bedrockagentcore_apikey_credential_provider` is created. OAuth2 providers are explicitly skipped with a comment about secrets. However, the Terraform resource exists (per issue #43424) and can handle sensitive values with `sensitive = true` attributes, keeping them out of plan output while still managing the resource lifecycle.

---

### 3.6 Missing `aws_bedrockagentcore_workload_provider`

Listed in provider issue #43424. Workload providers enable non-agent workloads (e.g., Lambda functions, ECS tasks) to access AgentCore resources. Not created anywhere in our modules.

---

## 4. HIGH: Security Issues

### 4.1 ECR Encryption Uses AES256, Not KMS

**File:** `modules/agents/ecr.tf`

```hcl
encryption_configuration {
  encryption_type = "AES256"
}
```

All other data stores (DynamoDB, S3, SQS) use customer-managed KMS keys. ECR should too, for consistency with the platform's encryption strategy. Use the `storage_kms_key_arn` from the platform module.

---

### 4.2 Agent IAM Roles Use Wildcard Resources

**File:** `modules/agents/iam.tf`

The following permissions use `resources = ["*"]`:
- `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` — Should scope to specific model ARNs derived from the agent blueprint's `model_id`
- `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` — Should scope to `/aws/bedrock-agentcore/{prefix}-{env}-{agent_id}*`

Note: `ecr:GetAuthorizationToken` and `xray:Put*` must use `*` per API requirements — these are OK.

---

### 4.3 VPC Endpoints Missing `bedrock-agentcore` Service

**File:** `modules/platform/modules/security/vpc_endpoints.tf`

Interface endpoints are created for `bedrock` and `bedrock-runtime`, but NOT for `bedrock-agentcore`. If the `bedrock-agentcore` VPC endpoint service exists in the region, agents running in PRIVATE network mode will need it for AgentCore API calls (runtime management, gateway access, memory operations).

**Verify:** Check if `com.amazonaws.{region}.bedrock-agentcore` is a valid VPC endpoint service.

---

## 5. HIGH: No Backend Configuration

No `backend.tf` file exists in any module. Terraform state is stored locally by default.

**Impact:**
- State file is not shared across team members
- No state locking — concurrent applies can corrupt state
- State file may contain secrets (KMS key ARNs, resource IDs) stored on local disk

**Needed:** S3 backend with DynamoDB locking. The backend config itself should be in the consuming repo (domain repos), not in the module source, but the platform module should document the expected backend pattern.

---

## 6. MEDIUM: Cross-Region Provider

**File:** `modules/platform/providers.tf`

`bedrock_region` (us-west-2) differs from `aws_region` (eu-west-1), but no aliased provider exists. Currently this is passed as an environment variable (`BEDROCK_REGION`) to agent runtimes, so the SDK handles cross-region calls at runtime. However, if any future Terraform resource needs to be created in the Bedrock region (e.g., model customization, guardrails), a provider alias will be needed.

**Status:** Not blocking today, but worth tracking.

---

## 7. MEDIUM: CodeBuild `NO_SOURCE` Pattern

**File:** `modules/agents/codebuild.tf`

```hcl
source {
  type = "NO_SOURCE"
}
```

The buildspec runs `docker build .` but with `NO_SOURCE` there is no source code available. The intended workflow is:
1. Domain repo triggers CodeBuild externally (via CLI/SDK)
2. Source is provided at trigger time via `sourceLocationOverride`

This is a valid pattern for externally-triggered builds, but:
- The buildspec should handle the case where source is injected via override
- Documentation should clarify this workflow for domain repo consumers
- Consider adding `codebuild_source_bucket` wiring (variable exists but isn't used)

---

## 8. MEDIUM: Step Functions Integration

### 8.1 AgentCore Integration ARN

**File:** `modules/workflows/state_machines.tf`

```hcl
Resource = "arn:aws:states:::bedrock-agentcore:invokeAgentRuntime"
```

This is the Step Functions optimized integration pattern. Verify:
1. This exact service integration exists — `bedrock-agentcore` is a new service, the SFN integration may use a different resource ARN
2. The `AgentRuntimeArn` parameter name matches the API
3. `SessionState.Prompt.$` JSONPath is correct for the API shape

If the integration doesn't exist, tasks would need to use `arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime` (SDK integration pattern) instead.

---

### 8.2 Parallel State Result Merging

**File:** `modules/workflows/state_machines.tf`

Parallel states set `ResultPath = "$.parallel_results"` which overwrites the input. If downstream states need both the original input and parallel results, consider using `ResultSelector` to merge them.

---

## 9. MEDIUM: Memory Strategy Types

**File:** `modules/agents/memory_strategies.tf`

```hcl
strategy_type_map = {
  "SUMMARY"         = "SUMMARIZATION"
  "SUMMARIZATION"   = "SUMMARIZATION"
  "SEMANTIC"        = "SEMANTIC"
  "USER_PREFERENCE" = "USER_PREFERENCE"
}
```

CloudFormation example shows `ShortTermMemory` as a strategy type. The full list of valid values may include types not in our mapping. If the API rejects our values, strategy creation will fail silently (Terraform will report the API error).

**Verify:** Check the [MemoryStrategy property type documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-bedrockagentcore-memory-memorystrategy.html).

---

## 10. MEDIUM: DynamoDB Missing GSIs

**File:** `modules/platform/modules/data/main.tf`

Tables are created with hash/range keys only. Common query patterns will need GSIs:

| Table | Likely GSI | Purpose |
|-------|-----------|---------|
| `artifacts` | `agent_id-created_at-index` | List artifacts by agent |
| `audit_log` | `agent_id-timestamp-index` | Agent audit trail |
| `run_history` | `agent_id-started_at-index` | Agent run history |
| `run_history` | `status-started_at-index` | Find runs by status |

Without GSIs, these queries require full table scans, which are expensive and slow at scale.

---

## 11. LOW: Minor Issues

### 11.1 Duplicate Tag Merging

**File:** `modules/platform/locals.tf`

```hcl
tags = merge(var.tags, {
  Environment = var.environment
  Project     = var.resource_prefix
  ManagedBy   = "terraform"
})
```

These same tags are also set as `default_tags` in `providers.tf`. Resources will have duplicate tag sources. This works but is redundant — `default_tags` already applies them.

### 11.2 Gateway `authorizer_configuration` Missing NONE Type

**File:** `modules/platform/modules/agentcore/gateway.tf`

CloudFormation shows `AuthorizerType` allows `CUSTOM_JWT | AWS_IAM | NONE`. Our validation only allows `AWS_IAM` and `CUSTOM_JWT`. The `NONE` type (no auth) may be useful for dev/testing.

### 11.3 No `moved` Blocks

If resource addresses change during refactoring, `moved` blocks prevent destroy-and-recreate cycles. Worth adding proactively for key resources.

### 11.4 Missing `description` on Memory Resource

**File:** `modules/platform/modules/agentcore/memory.tf`

CloudFormation shows optional `Description` field. Our memory resource doesn't set it — minor but helpful for console identification.

---

## Block 1 — Completion Notes

**Date:** 2026-03-21

All 5 critical findings resolved. Provider schema verified via `terraform providers schema -json`.

### Block 1 Fixes Applied

| Finding | Fix Applied |
|---------|-------------|
| 1. Missing `placeholder.zip` | Created at `modules/platform/modules/api/placeholder.zip` |
| 2. `protocol_configuration` | Confirmed as block. Renamed `protocol` → `server_protocol` per provider schema. Removed hardcoded `"HTTP"` default |
| 3. Memory `event_expiry_duration` | Changed validation from `>= 1` to `>= 3` per AWS API minimum |
| 4. `credential_provider_configurations` | Renamed to singular `credential_provider_configuration` block. Uses `gateway_iam_role {}` sub-block |
| 5. `tool_schema`/`inline_payload` | Fixed nesting: `lambda_target_configuration` → `mcp { lambda {} }`. `inline_payload` kept singular (confirmed by schema). Removed `inline_tool_definitions` list — each tool is a separate `inline_payload` block |

### Additional Fixes (discovered during `terraform validate`)

These were NOT in the original audit but blocked validation:

| Fix | File | Issue |
|-----|------|-------|
| Resource type rename | `agents/identity_providers.tf` | `apikey` → `api_key` in resource type name |
| Add `api_key_wo` | `agents/identity_providers.tf` | Resource requires `api_key` or `api_key_wo` — was missing |
| Remove invalid `credential_provider_vendor` | `agents/identity_providers.tf` | Attribute does not exist in provider schema |
| Remove unsupported `tags` | `agents/memory_strategies.tf` | Provider does not support tags on this resource |
| Fix VPC block name | `agents/runtime.tf` | `vpc_configuration` → `network_mode_config`, `subnet_ids` → `subnets`, `security_group_ids` → `security_groups` |
| Fix authorizer nesting | `platform/modules/agentcore/gateway.tf` | JWT config must be inside `custom_jwt_authorizer {}` sub-block |
| Fix `network_configuration` | `platform/modules/agentcore/tools.tf` | Changed from string to block with `network_mode` attribute |
| Fix output attributes | `platform/modules/agentcore/outputs.tf` | `.id` → `.gateway_id`, `.arn` → `.gateway_arn`, `.id` → `.code_interpreter_id`/`.browser_id` |

Both `modules/platform` and `modules/agents` now pass `terraform validate` (only deprecation warnings on `data.aws_region.current.name`).

---

## Block 2 — Completion Notes

**Date:** 2026-03-21

7 of 8 findings resolved. Finding 8 (Gateway `policy_engine_configuration`) skipped — attribute not present in Terraform AWS provider schema (>= 6.21). Provider schema verified via `terraform providers schema -json`.

### Block 2 Fixes Applied

| Finding | Fix Applied |
|---------|-------------|
| 6. Runtime Endpoint | Added `aws_bedrockagentcore_agent_runtime_endpoint` per agent, SSM parameter, output |
| 7. Gateway KMS | Added `kms_key_arn` to gateway resource, wired to `data_kms_key_arn` from security module |
| 8. Gateway Policy Engine | SKIPPED — `policy_engine_configuration` not in provider schema yet |
| 9. Lifecycle Configuration | Added `lifecycle_configuration` attribute (conditional on blueprint), `ignore_changes` workaround for bug #45290 |
| 10. ECR KMS | Changed to conditional `KMS`/`AES256` via `storage_kms_key_arn` variable, added storage KMS IAM statement |
| 11. IAM Scoping | Scoped `bedrock:InvokeModel` to blueprint `model_id` ARN, scoped CloudWatch Logs to agent-specific groups, split ECR auth (wildcard) from image pull (scoped) |
| 12. VPC Endpoint | Added `bedrock_agentcore` to `interface_endpoints` locals map (may not be available in all regions) |
| 13. OAuth2 Provider | Added `aws_bedrockagentcore_oauth2_credential_provider` with SSM-backed secrets, `custom_oauth2_provider_config`, `ignore_changes` on provider config |

---

## Block 3 — Completion Notes

**Date:** 2026-03-21

8 of 8 findings resolved. Finding 14 (backend configuration documentation) is out of scope for Block 3 — it belongs in domain repo documentation, not the platform module.

### Block 3 Fixes Applied

| Finding | Fix Applied |
|---------|-------------|
| 15. SFN Integration | Switched from non-existent optimized integration to SDK pattern (`aws-sdk:bedrockagentcore:invokeAgentRuntime`). Updated parameters: `SessionState.Prompt` → `Payload` |
| 16. DynamoDB GSIs | Added 4 GSIs across 3 tables (artifacts, audit_log, run_history). Extended locals with `gsis` list and computed `table_attributes` for deduplication. Dynamic `global_secondary_index` blocks with conditional provisioned capacity |
| 17. Memory Strategy Types | Added `CUSTOM` and `EPISODIC` to `strategy_type_map`. Updated header comments listing all 5 API types |
| 18. CodeBuild Documentation | Added workflow documentation block explaining NO_SOURCE / sourceLocationOverride pattern and codebuild_source_bucket IAM wiring |
| 19. Cross-Region Provider | Added `aws.bedrock` provider alias for `var.bedrock_region` with matching `default_tags`. No existing resources switched — available for future use |
| 20. Gateway NONE Auth | Added `NONE` to `gateway_auth_type` validation in both agentcore sub-module and root platform variables. Gateway resource dynamic block already handles NONE correctly |
| 21. Duplicate Tags | Removed duplicate Environment/Project/ManagedBy from `local.tags` — already applied via `default_tags` in provider. `local.tags` now passes through `var.tags` only |
| 22. Memory Description | Added `memory_description` variable with pass-through wiring (agentcore variables → root variables → main.tf). Memory resource sets `description` conditionally (null when empty) |

---

## 12. Summary — Action Items by Priority

### Must Fix (Will fail terraform plan/apply)

| # | Finding | Severity | Files |
|---|---------|----------|-------|
| 1 | ~~Create `placeholder.zip` for Lambda~~ | DONE | `modules/platform/modules/api/placeholder.zip` |
| 2 | ~~Verify `protocol_configuration` block vs string~~ | DONE | `modules/agents/runtime.tf` |
| 3 | ~~Fix memory `event_expiry_duration` min validation (3 not 1)~~ | DONE | `modules/platform/modules/agentcore/variables.tf` |
| 4 | ~~Verify `credential_provider_configurations` block vs attribute~~ | DONE | `modules/agents/gateway_targets.tf` |
| 5 | ~~Verify `tool_schema`/`inline_payload` nesting~~ | DONE | `modules/agents/gateway_targets.tf` |

### Should Fix (Missing functionality or security)

| # | Finding | Severity | Files |
|---|---------|----------|-------|
| 6 | ~~Add `aws_bedrockagentcore_runtime_endpoint`~~ | DONE | `modules/agents/runtime.tf` |
| 7 | ~~Add Gateway `kms_key_arn`~~ | DONE | `modules/platform/modules/agentcore/gateway.tf` |
| 8 | Add Gateway `policy_engine_configuration` | SKIPPED | Not in provider schema (aws >= 6.21). Revisit when provider adds support |
| 9 | ~~Add Runtime `lifecycle_configuration`~~ | DONE | `modules/agents/runtime.tf` |
| 10 | ~~ECR: switch AES256 to KMS~~ | DONE | `modules/agents/ecr.tf` |
| 11 | ~~Scope agent IAM `bedrock:InvokeModel` to model ARNs~~ | DONE | `modules/agents/iam.tf` |
| 12 | ~~Add VPC endpoint for `bedrock-agentcore`~~ | DONE | `modules/platform/modules/security/vpc_endpoints.tf` |
| 13 | ~~Add `aws_bedrockagentcore_oauth2_credential_provider`~~ | DONE | `modules/agents/identity_providers.tf` |

### Should Address (Best practice / completeness)

| # | Finding | Severity | Files |
|---|---------|----------|-------|
| 14 | Document backend configuration pattern | MEDIUM | New `docs/` or README |
| 15 | ~~Fix SFN to SDK integration pattern (optimized integration does not exist)~~ | DONE | `modules/workflows/state_machines.tf` |
| 16 | ~~Add DynamoDB GSIs for common query patterns~~ | DONE | `modules/platform/modules/data/main.tf` |
| 17 | ~~Verify and update memory strategy type values~~ | DONE | `modules/agents/memory_strategies.tf` |
| 18 | ~~Document CodeBuild `NO_SOURCE` / override workflow~~ | DONE | `modules/agents/codebuild.tf` |
| 19 | ~~Add cross-region Bedrock provider alias~~ | DONE | `modules/platform/providers.tf` |
| 20 | ~~Add `NONE` to Gateway authorizer_type validation~~ | DONE | `modules/platform/modules/agentcore/variables.tf` |
| 21 | ~~Remove duplicate tags in locals.tf~~ | DONE | `modules/platform/locals.tf` |
| 22 | ~~Add `description` to Memory resource~~ | DONE | `modules/platform/modules/agentcore/memory.tf` |
---

## 13. References

- [AWS::BedrockAgentCore::Gateway CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrockagentcore-gateway.html)
- [AWS::BedrockAgentCore::Runtime CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrockagentcore-runtime.html)
- [AWS::BedrockAgentCore::Memory CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrockagentcore-memory.html)
- [Terraform AWS Provider — AgentCore Support Issue #43424](https://github.com/hashicorp/terraform-provider-aws/issues/43424)
- [Terraform AWS Provider — Runtime lifecycle_configuration Bug #45290](https://github.com/hashicorp/terraform-provider-aws/issues/45290)
- [Terraform AWS Provider — Gateway Target missing grant_type #46128](https://github.com/hashicorp/terraform-provider-aws/issues/46128)
- [Terraform AWS Provider — Gateway Target MCP server support #44976](https://github.com/hashicorp/terraform-provider-aws/issues/44976)
- [Deploy AI Agents with Terraform — AWS Bedrock AgentCore Guide](https://www.pierreange.ai/blog/deploy-ai-agents-aws-bedrock-agentcore-terraform)
