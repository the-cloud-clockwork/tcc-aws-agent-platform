# Infrastructure Patch — Post-Audit Sweep

> Deep sweep of all Terraform modules after Blocks 1–3 completion.
> Covers skipped INFRA.md findings, new security/operational gaps, and deprecated attributes.
>
> **Date:** 2026-03-21
> **Provider:** hashicorp/aws >= 6.21
> **Scope:** All 3 modules (platform, agents, workflows)

---

## Severity Legend

| Level | Meaning |
|-------|---------|
| **CRITICAL** | Security gap or will cause apply failures |
| **HIGH** | Missing functionality, operational risk |
| **MEDIUM** | Best practice violation, hardening gap |
| **LOW** | Minor improvement, cleanup |

---

## Part 1 — Skipped INFRA.md Items

### S1. Gateway `policy_engine_configuration` (INFRA Finding 8)

**Status:** SKIPPED in Block 2 — attribute not in Terraform AWS provider schema (>= 6.21)

**Why it was skipped:** `terraform providers schema -json` confirmed the `aws_bedrockagentcore_gateway` resource does not expose a `policy_engine_configuration` attribute. The Python SDK (`core/src/agent_core/policy/client.py`) has full PolicyClient/Cedar support, but no Terraform resource exists to wire policies at the infrastructure level.

**CloudFormation schema** defines `PolicyEngineConfiguration` on `AWS::BedrockAgentCore::Gateway` with:
- `PolicyEngineMode`: `ENFORCE` or `LOG_ONLY`
- `PolicyResourceArn`: ARN of the policy engine

**How to patch (when provider adds support):**

```hcl
# modules/platform/modules/agentcore/gateway.tf — add to gateway resource:
dynamic "policy_engine_configuration" {
  for_each = var.gateway_policy_mode != "" ? [1] : []
  content {
    policy_engine_mode = var.gateway_policy_mode  # ENFORCE | LOG_ONLY
  }
}

# modules/platform/modules/agentcore/variables.tf — add:
variable "gateway_policy_mode" {
  description = "Policy engine mode for Gateway. Empty string to skip. ENFORCE or LOG_ONLY."
  type        = string
  default     = ""
  validation {
    condition     = var.gateway_policy_mode == "" || contains(["ENFORCE", "LOG_ONLY"], var.gateway_policy_mode)
    error_message = "gateway_policy_mode must be empty, ENFORCE, or LOG_ONLY."
  }
}
```

**Interim workaround:** PolicyClient in the SDK manages policies at runtime. No Terraform action needed until provider support lands. Track [#43424](https://github.com/hashicorp/terraform-provider-aws/issues/43424).

---

### S2. Backend Configuration Pattern (INFRA Finding 14)

**Status:** Not in any block — out of scope for platform module

**Why it was skipped:** Backend configuration belongs in the **consuming repository** (domain repos), not in the module source. The platform module is consumed via `source = "git::repo.git//modules/platform"` — each consumer manages its own state.

**What domain repos need:**

```hcl
# Domain repo: terraform/backend.tf
terraform {
  backend "s3" {
    bucket         = "<project>-tf-state-<account_id>"
    key            = "<environment>/platform.tfstate"
    region         = "eu-west-1"
    encrypt        = true
    dynamodb_table = "<project>-tf-locks"
  }
}
```

**How to patch:** Document the backend pattern in platform module README or a `BACKEND.md` guide. No code changes needed in platform module.

---

### S3. Missing `aws_bedrockagentcore_workload_provider` (INFRA Finding 3.6)

**Status:** Listed in INFRA.md section 3.6, never assigned to any block

**What it is:** Workload providers enable non-agent workloads (Lambda, ECS tasks, Step Functions) to access AgentCore resources — invoke agents, call gateway tools, access memory.

**Why it was missed:** Not included in Block 3 scope. The resource exists in provider >= 6.21.

**Where it belongs:** `modules/agents/` — workload providers are per-deployment, not platform-wide.

**How to patch:**

```hcl
# modules/agents/workload_providers.tf (new file)
resource "aws_bedrockagentcore_workload_provider" "this" {
  for_each = {
    for type in var.workload_provider_types : type => type
  }

  name          = "${local.name_prefix}-${lower(each.value)}-workload"
  workload_type = each.value  # LAMBDA | ECS_TASK | STEP_FUNCTIONS_EXECUTION

  tags = merge(local.tags, {
    Name = "${local.name_prefix}-${lower(each.value)}-workload"
    Type = "workload-provider"
  })
}

# modules/agents/variables.tf — add:
variable "workload_provider_types" {
  description = "Workload types to register (LAMBDA, ECS_TASK, STEP_FUNCTIONS_EXECUTION)"
  type        = list(string)
  default     = []
}
```

**Priority:** MEDIUM — needed when domain repos run Lambda/ECS workloads that invoke agents.

---

## Part 2 — New Findings (Deep Sweep)

### Security

#### P1. ECR Tag Mutability Set to MUTABLE (HIGH)

**File:** `modules/agents/ecr.tf`

Docker image tags can be overwritten after push, allowing tag reassignment attacks. All other security measures (KMS encryption, IAM scoping) are undermined if an attacker can replace `:latest` with a compromised image.

**Fix:** Change `image_tag_mutability = "MUTABLE"` → `"IMMUTABLE"`. Requires a variable to allow override if domain repos need mutable tags.

```hcl
variable "ecr_image_tag_mutability" {
  type    = string
  default = "IMMUTABLE"
  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.ecr_image_tag_mutability)
    error_message = "Must be MUTABLE or IMMUTABLE."
  }
}
```

---

#### P2. Workflows IAM Falls Back to Wildcard Runtime ARN (HIGH)

**File:** `modules/workflows/iam.tf`

When `var.agent_runtime_arns` doesn't contain an agent ID, the policy falls back to `arn:aws:bedrock-agentcore:REGION:ACCOUNT:*`, granting access to ALL runtimes.

**Fix:** Remove the wildcard fallback. Require explicit runtime ARN mapping:

```hcl
Resource = [
  for agent_id in ... :
  var.agent_runtime_arns[agent_id]  # Fail if missing — no silent wildcard
]
```

---

#### P3. Missing CloudWatch Log Encryption (HIGH)

**Files:**
- `modules/workflows/state_machines.tf` — SFN log groups have no KMS encryption
- `modules/platform/modules/observability/main.tf` — Pipeline log group has no KMS encryption

Platform uses 5 KMS keys with envelope encryption for all data stores. Log groups are the exception — they use AWS-managed encryption only.

**Fix:** Add `kms_key_id` to all `aws_cloudwatch_log_group` resources. Wire the `data_kms_key_arn` from the security module.

---

#### P4. Missing S3 Access Logging (MEDIUM)

**File:** `modules/platform/modules/data/s3.tf`

Three S3 buckets (artifacts, prompt_registry, historical_data) have no access logging. Cannot track who accessed what data.

**Fix:** Add `aws_s3_bucket_logging` resource for each bucket, targeting a dedicated logging bucket or a shared logging prefix.

---

### Operational

#### P5. Missing CloudWatch Alarms (HIGH)

**File:** `modules/platform/modules/observability/main.tf`

SNS topic and dashboard exist but NO CloudWatch alarms. Missing alerting for:
- Lambda error rate / throttling
- DynamoDB read/write throttling
- SQS queue depth (DLQ messages)
- API Gateway 5xx errors

**Fix:** Add `aws_cloudwatch_metric_alarm` resources for critical metrics, wired to the existing SNS alert topic.

---

#### P6. Hardcoded CloudFront Cache Policy ID (MEDIUM)

**File:** `modules/platform/modules/data/cloudfront.tf`

```hcl
cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
```

Hardcoded AWS managed policy ID. Should use a data source.

**Fix:**
```hcl
data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}
# Reference: data.aws_cloudfront_cache_policy.caching_optimized.id
```

---

#### P7. Hardcoded Lambda Memory and Timeout (MEDIUM)

**File:** `modules/platform/modules/api/main.tf`

```hcl
memory_size = 512
timeout     = 30
```

Should be variables per the "no hardcoded defaults" rule.

---

#### P8. Hardcoded Cognito Token Validity (MEDIUM)

**File:** `modules/platform/modules/agentcore/cognito.tf`

Token validity periods (1h access, 1h ID, 30d refresh) are hardcoded. Should be variables.

---

#### P9. Missing ECR Lifecycle Policy (MEDIUM)

**File:** `modules/agents/ecr.tf`

No lifecycle policy to expire old images. ECR costs grow unbounded as images accumulate.

**Fix:** Add `aws_ecr_lifecycle_policy` with rules to keep N most recent images.

```hcl
resource "aws_ecr_lifecycle_policy" "agent" {
  for_each   = local.blueprints
  repository = aws_ecr_repository.agent[each.key].name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
```

---

#### P10. Unused Variables (LOW)

**Agents module** (`modules/agents/variables.tf`):
- `gateway_role_arn` — declared, never referenced
- `vpc_id` — declared, never referenced

**Workflows module** (`modules/workflows/variables.tf`):
- `aws_region` — declared, `local.region` used instead
- `ssm_root_path` — declared, never referenced

**Fix:** Remove or use. If reserved for future use, add a comment.

---

#### P11. Missing Outputs (LOW)

- **Agents module:** `ecr_repository_arns` not exposed (only URLs)
- **Workflows module:** SFN execution role ARNs and EventBridge rule names not exposed

---

### Deprecated Attributes

#### P12. `data.aws_region.current.name` → `.id` (LOW)

15 occurrences across 6 files. AWS provider >= 6.0 deprecated `.name` in favor of `.id` (functionally identical). Causes deprecation warnings on every validate/plan.

**Files:**
| File | Count |
|------|-------|
| `modules/platform/locals.tf` | 1 |
| `modules/platform/modules/security/main.tf` | 1 |
| `modules/platform/modules/observability/main.tf` | 3 |
| `modules/agents/codebuild.tf` | 4 |
| `modules/agents/iam.tf` | 5 |
| `modules/workflows/locals.tf` | 1 |

**Fix:** Global replace `data.aws_region.current.name` → `data.aws_region.current.id`

---

## Part 3 — Summary

### Skipped Items

| # | Item | Why Skipped | How to Patch | Priority |
|---|------|-------------|--------------|----------|
| S1 | Gateway policy_engine_configuration | Not in provider schema | Wait for provider, or CloudControl API | LOW (blocked) |
| S2 | Backend configuration docs | Belongs in domain repo | Document pattern in README/BACKEND.md | LOW |
| S3 | Workload provider resource | Not assigned to any block | New file in agents module | MEDIUM |

### New Findings

| # | Finding | Severity | Files | Effort |
|---|---------|----------|-------|--------|
| P1 | ECR tag mutability MUTABLE→IMMUTABLE | HIGH | `agents/ecr.tf` | Small |
| P2 | Workflow IAM wildcard fallback | HIGH | `workflows/iam.tf` | Small |
| P3 | Missing log group KMS encryption | HIGH | `workflows/state_machines.tf`, `observability/main.tf` | Medium |
| P4 | Missing S3 access logging | MEDIUM | `data/s3.tf` | Medium |
| P5 | Missing CloudWatch alarms | HIGH | `observability/main.tf` | Large |
| P6 | Hardcoded CloudFront cache policy ID | MEDIUM | `data/cloudfront.tf` | Small |
| P7 | Hardcoded Lambda memory/timeout | MEDIUM | `api/main.tf` | Small |
| P8 | Hardcoded Cognito token validity | MEDIUM | `agentcore/cognito.tf` | Small |
| P9 | Missing ECR lifecycle policy | MEDIUM | `agents/ecr.tf` | Small |
| P10 | Unused variables | LOW | `agents/variables.tf`, `workflows/variables.tf` | Small |
| P11 | Missing outputs | LOW | `agents/outputs.tf`, `workflows/outputs.tf` | Small |
| P12 | Deprecated `.name` → `.id` | LOW | 6 files, 15 occurrences | Small |

### Totals

- **Skipped items:** 3 (1 blocked by provider, 1 documentation, 1 new resource)
- **New findings:** 12 (3 HIGH, 5 MEDIUM, 4 LOW)
- **Estimated effort:** ~2 implementation blocks

### Recommended Block Structure

**Block 4 — Security Hardening:**
P1 (ECR immutable), P2 (workflow IAM), P3 (log encryption), P12 (deprecation fix)

**Block 5 — Operational Hardening:**
P5 (alarms), P6 (CloudFront data source), P7 (Lambda vars), P8 (Cognito vars), P9 (ECR lifecycle), P10 (unused vars), P11 (outputs), S3 (workload provider)

