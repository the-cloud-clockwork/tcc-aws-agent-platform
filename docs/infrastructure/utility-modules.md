---
title: Utility Modules
nav_order: 4
parent: "Infrastructure (Terraform)"
---

# Utility Modules

The AWS Agent Platform ships four utility modules alongside the three core modules. They encode common AWS infrastructure patterns with consistent naming, tagging, encryption, and alarming conventions. The platform module uses all four internally, and domain repos can reference them directly via `git::` source for their own Lambdas and S3 buckets.

| Module | Path | What it provisions |
|--------|------|--------------------|
| [`lambda`](#lambda-module) | `modules/lambda/` | Lambda function + IAM role + X-Ray + CloudWatch log group |
| [`lambda_alarms`](#lambda_alarms-module) | `modules/lambda_alarms/` | Errors alarm + Duration p99 alarm per Lambda |
| [`scheduled_lambda`](#scheduled_lambda-module) | `modules/scheduled_lambda/` | EventBridge rule + target + Lambda permission |
| [`s3_encrypted_bucket`](#s3_encrypted_bucket-module) | `modules/s3_encrypted_bucket/` | S3 bucket with versioning, KMS SSE, public-access block |

---

## `lambda` Module

Provisions a complete, production-ready Lambda function with consistent defaults:

- **Archive** — zips `source_dir` at plan time (`archive_file`); hash-based deploy triggers on change.
- **IAM role** — `AWSLambdaBasicExecutionRole` (non-VPC) or `AWSLambdaVPCAccessExecutionRole` (VPC); `AWSXRayDaemonWriteAccess` always attached.
- **X-Ray** — active tracing enabled unconditionally.
- **CloudWatch log group** — `/aws/lambda/<function-name>`, configurable retention, optional KMS encryption.
- **Additional inline policies** — passed as a list of JSON policy documents.

**Defaults:** `runtime = python3.12`, `architectures = ["arm64"]`, `memory_size = 256`, `timeout = 30`.

### Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `function_name` | `string` | — | Function name (without prefix) |
| `source_dir` | `string` | — | Path to source directory to zip |
| `resource_prefix` | `string` | — | Prefix for all resource names |
| `handler` | `string` | `"handler.handler"` | Lambda handler entry point |
| `runtime` | `string` | `"python3.12"` | Lambda runtime identifier |
| `memory_size` | `number` | `256` | Memory in MB |
| `timeout` | `number` | `30` | Timeout in seconds |
| `architectures` | `list(string)` | `["arm64"]` | Instruction set architectures |
| `environment_variables` | `map(string)` | `{}` | Environment variables |
| `vpc_enabled` | `bool` | `false` | Attach to a VPC |
| `subnet_ids` | `list(string)` | `[]` | Subnet IDs (required when `vpc_enabled = true`) |
| `security_group_ids` | `list(string)` | `[]` | Security group IDs (required when `vpc_enabled = true`) |
| `kms_key_arn` | `string` | `""` | KMS key ARN for log group encryption |
| `log_retention_days` | `number` | `14` | CloudWatch log retention in days |
| `additional_policies` | `list(string)` | `[]` | IAM policy JSON documents attached as inline policies |
| `tags` | `map(string)` | `{}` | Resource tags |

### Outputs

| Output | Description |
|--------|-------------|
| `function_name` | Lambda function name |
| `function_arn` | Lambda function ARN |
| `invoke_arn` | Lambda invoke ARN (for API Gateway integrations) |
| `role_arn` | IAM role ARN |
| `role_name` | IAM role name |
| `log_group_name` | CloudWatch log group name |

### Usage Example

```hcl
module "ingest_lambda" {
  source = "git::https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform.git//modules/lambda?ref=v1.0.0"

  resource_prefix = "myplatform-dev"
  function_name   = "data-ingest"
  source_dir      = "${path.module}/src/ingest"
  handler         = "ingest.handler"
  timeout         = 60
  memory_size     = 512
  kms_key_arn     = var.kms_key_arn

  environment_variables = {
    TABLE_NAME = var.table_name
    BUCKET     = var.bucket_name
  }

  additional_policies = [
    jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem"]
        Resource = var.table_arn
      }]
    })
  ]

  tags = { Project = "my-platform" }
}
```

---

## `lambda_alarms` Module

Provisions a pair of CloudWatch alarms for every Lambda in a supplied map:

- **Errors alarm** — triggers when `Sum(Errors)` over 5 minutes exceeds 0 (any error fires the alarm).
- **Duration alarm** — triggers when `p99(Duration)` over 5 minutes exceeds 75% of the function's configured timeout. Three consecutive evaluation periods are required to fire.

Both alarms send to the supplied `alarm_actions` ARN list (e.g. an SNS topic).

### Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `lambdas` | `map(object({ function_name: string, timeout: number }))` | — | Map of logical name → `{function_name, timeout}` |
| `alarm_actions` | `list(string)` | — | ARNs to notify when alarms transition to ALARM state |
| `resource_prefix` | `string` | — | Prefix for alarm names |
| `tags` | `map(string)` | `{}` | Resource tags |

### Usage Example

```hcl
module "lambda_alarms" {
  source = "git::https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform.git//modules/lambda_alarms?ref=v1.0.0"

  resource_prefix = "myplatform-dev"
  alarm_actions   = [module.platform.alert_topic_arn]

  lambdas = {
    data-ingest = {
      function_name = module.ingest_lambda.function_name
      timeout       = 60
    }
    data-export = {
      function_name = module.export_lambda.function_name
      timeout       = 30
    }
  }

  tags = { Project = "my-platform" }
}
```

---

## `scheduled_lambda` Module

Encapsulates the three resources required to invoke a Lambda on a schedule:

1. `aws_cloudwatch_event_rule` — EventBridge rule with a `cron(...)` or `rate(...)` expression.
2. `aws_cloudwatch_event_target` — wires the rule to the Lambda ARN.
3. `aws_lambda_permission` — grants EventBridge permission to invoke the function.

### Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `name` | `string` | — | Logical name (used in resource names) |
| `schedule_expression` | `string` | — | EventBridge expression: `rate(1 hour)` or `cron(0 6 * * ? *)` |
| `function_name` | `string` | — | Lambda function name |
| `function_arn` | `string` | — | Lambda function ARN |
| `resource_prefix` | `string` | — | Prefix for resource names |
| `description` | `string` | `""` | Human-readable rule description |
| `tags` | `map(string)` | `{}` | Resource tags |

### Usage Example

```hcl
# Run the ingest Lambda every hour
module "ingest_schedule" {
  source = "git::https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform.git//modules/scheduled_lambda?ref=v1.0.0"

  resource_prefix     = "myplatform-dev"
  name                = "hourly-ingest"
  description         = "Trigger data ingest every hour"
  schedule_expression = "rate(1 hour)"
  function_name       = module.ingest_lambda.function_name
  function_arn        = module.ingest_lambda.function_arn

  tags = { Project = "my-platform" }
}

# Run a nightly report Lambda at 06:00 UTC
module "nightly_report" {
  source = "git::https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform.git//modules/scheduled_lambda?ref=v1.0.0"

  resource_prefix     = "myplatform-dev"
  name                = "nightly-report"
  description         = "Nightly summary report at 06:00 UTC"
  schedule_expression = "cron(0 6 * * ? *)"
  function_name       = module.report_lambda.function_name
  function_arn        = module.report_lambda.function_arn

  tags = { Project = "my-platform" }
}
```

---

## `s3_encrypted_bucket` Module

Provisions a production-ready S3 bucket with:

- **Versioning** — always enabled.
- **KMS SSE** — `aws:kms` with `bucket_key_enabled = true` (reduces KMS API calls).
- **Public access block** — all four settings (`block_public_acls`, `block_public_policy`, `ignore_public_acls`, `restrict_public_buckets`) set to `true`.
- **SSM parameter** — optionally writes the bucket name to a specified SSM path for cross-module consumption.

### Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `bucket_name` | `string` | — | S3 bucket name (globally unique) |
| `kms_key_arn` | `string` | — | KMS key ARN for server-side encryption |
| `ssm_path` | `string` | `""` | SSM parameter path to store the bucket name. Empty to skip. |
| `force_destroy` | `bool` | `false` | Allow Terraform to destroy the bucket even if it contains objects |
| `tags` | `map(string)` | `{}` | Resource tags |

### Outputs

| Output | Description |
|--------|-------------|
| `bucket_name` | S3 bucket name |
| `bucket_arn` | S3 bucket ARN |
| `bucket_id` | S3 bucket ID (same as name) |

### Usage Example

```hcl
module "domain_data_bucket" {
  source = "git::https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform.git//modules/s3_encrypted_bucket?ref=v1.0.0"

  bucket_name   = "myplatform-dev-domain-data-${data.aws_caller_identity.current.account_id}"
  kms_key_arn   = module.platform.storage_kms_key_arn
  force_destroy = var.environment == "dev"
  ssm_path      = "/myplatform/dev/buckets/domain-data/name"

  tags = { Project = "my-platform" }
}
```

Then grant agents read access via the agents module:

```hcl
module "agents" {
  # ...
  extra_s3_read_bucket_arns = [module.domain_data_bucket.bucket_arn]
}
```

---

## Combining Utility Modules

A typical domain repo pattern — a scheduled Lambda that reads from a domain S3 bucket and writes results to DynamoDB, with alarms wired to the platform SNS topic:

```hcl
module "analysis_bucket" {
  source      = "git::https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform.git//modules/s3_encrypted_bucket?ref=v1.0.0"
  bucket_name = "myplatform-dev-analysis-${local.account_id}"
  kms_key_arn = module.platform.storage_kms_key_arn
  ssm_path    = "/myplatform/dev/buckets/analysis/name"
  tags        = local.tags
}

module "analysis_lambda" {
  source          = "git::https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform.git//modules/lambda?ref=v1.0.0"
  resource_prefix = local.prefix
  function_name   = "analysis"
  source_dir      = "${path.module}/src/analysis"
  timeout         = 300
  kms_key_arn     = module.platform.storage_kms_key_arn

  environment_variables = {
    BUCKET     = module.analysis_bucket.bucket_name
    TABLE_NAME = module.platform.table_names["run_history"]
  }

  additional_policies = [
    jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject"]
          Resource = "${module.analysis_bucket.bucket_arn}/*"
        },
        {
          Effect   = "Allow"
          Action   = ["dynamodb:PutItem"]
          Resource = module.platform.table_arns["run_history"]
        }
      ]
    })
  ]

  tags = local.tags
}

module "analysis_schedule" {
  source              = "git::https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform.git//modules/scheduled_lambda?ref=v1.0.0"
  resource_prefix     = local.prefix
  name                = "daily-analysis"
  schedule_expression = "cron(0 2 * * ? *)"
  function_name       = module.analysis_lambda.function_name
  function_arn        = module.analysis_lambda.function_arn
  tags                = local.tags
}

module "analysis_alarms" {
  source          = "git::https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform.git//modules/lambda_alarms?ref=v1.0.0"
  resource_prefix = local.prefix
  alarm_actions   = [module.platform.alert_topic_arn]

  lambdas = {
    analysis = {
      function_name = module.analysis_lambda.function_name
      timeout       = 300
    }
  }

  tags = local.tags
}
```
