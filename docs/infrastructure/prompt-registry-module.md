---
title: Prompt Registry Module
nav_order: 5
parent: "Infrastructure (Terraform)"
---

# Prompt Registry Module

Deploys a Lambda-backed Prompt Registry API for versioned prompt lifecycle management. Prompts are first-class software artifacts per [AWS AI-DLC Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-serverless/prompt-agent-and-model.html) — versioned, reviewed, and promoted through environments like code.

## What It Deploys

| Resource | Purpose |
|----------|---------|
| `aws_lambda_function` | Prompt Registry API handler (Python 3.12, arm64) |
| `aws_lambda_function_url` | IAM-authenticated endpoint for internal access |
| `aws_iam_role` + policies | DynamoDB read/write, S3 read/write, KMS decrypt |

The Lambda ships with `placeholder.zip`. Real handler code (`prompt_registry.handler.handler`) is deployed via CodeBuild after initial infrastructure provisioning.

Data storage (DynamoDB table + S3 bucket) is provisioned by the **platform data module**, not this module.

## Input Variables

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `resource_prefix` | `string` | Yes | Resource name prefix |
| `environment` | `string` | Yes | `dev`, `staging`, or `production` |
| `prompt_table_name` | `string` | Yes | DynamoDB table name for prompt metadata |
| `prompt_table_arn` | `string` | Yes | DynamoDB table ARN (for IAM) |
| `prompt_bucket_name` | `string` | Yes | S3 bucket name for prompt content |
| `prompt_bucket_arn` | `string` | Yes | S3 bucket ARN (for IAM) |
| `storage_kms_key_arn` | `string` | No | KMS key ARN for S3 encryption |
| `tags` | `map(string)` | No | Resource tags |

## Outputs

| Output | Description |
|--------|-------------|
| `prompt_registry_url` | Lambda Function URL (IAM auth) |
| `prompt_registry_lambda_arn` | Lambda ARN |
| `prompt_registry_lambda_name` | Lambda function name |

The URL is also exported to SSM at `/{ssm_prefix}/prompt-registry/url`.

## Wiring in Platform Module

The prompt registry module is wired in `modules/platform/main.tf`:

```hcl
module "prompt_registry" {
  source = "./modules/prompt_registry"

  resource_prefix     = var.resource_prefix
  environment         = var.environment
  prompt_table_name   = module.data.table_names["prompt_registry"]
  prompt_table_arn    = module.data.table_arns["prompt_registry"]
  prompt_bucket_name  = module.data.bucket_names["prompt_registry"]
  prompt_bucket_arn   = module.data.prompt_registry_bucket_arn
  storage_kms_key_arn = module.security.storage_kms_key_arn
  tags                = local.tags
}
```

## Agent Runtime Integration

The agents module accepts `prompt_registry_url` and injects it as `PROMPT_REGISTRY_URL` into all agent/MCP runtimes:

```hcl
module "agents" {
  source = "...//modules/agents"
  # ...
  prompt_registry_url = module.platform.prompt_registry_url
}
```

At runtime, `PromptRegistryClient` reads `PROMPT_REGISTRY_URL` and resolves prompts via the API. If the API is unavailable, it falls back to local files in the container.

## Domain Prompt Seeding

Domain repos keep prompt source files in git and seed them into the registry via Terraform:

```hcl
resource "aws_s3_object" "prompts" {
  for_each = local.prompts
  bucket   = module.platform.bucket_names["prompt_registry"]
  key      = "${each.key}/${local.prompt_version}.txt"
  source   = "${path.module}/../prompts/${each.value}"
  etag     = filemd5("${path.module}/../prompts/${each.value}")
}

resource "aws_dynamodb_table_item" "prompt_metadata" {
  for_each   = local.prompts
  table_name = module.platform.table_names["prompt_registry"]
  hash_key   = "prompt_key"
  range_key  = "version"
  item       = jsonencode({
    prompt_key = { S = each.key }
    version    = { S = local.prompt_version }
    status     = { S = "stable" }
    s3_key     = { S = "${each.key}/${local.prompt_version}.txt" }
    # ...
  })
  lifecycle { ignore_changes = [item] }
}
```

## Resolution Flow

`PromptRegistryClient` uses a three-tier resolution order:

```
Agent starts → BlueprintLoader reads prompt_ref from YAML
    ↓
PromptRegistryClient.get(prompt_ref)
    ↓
1. Direct Lambda invoke via boto3
   (when PROMPT_REGISTRY_FUNCTION env var is set — production path)
   Mode-gated: simulation/dev sees draft prompts; staging/production only stable.
    ↓ (if PROMPT_REGISTRY_FUNCTION is not set)
2. HTTP GET → PROMPT_REGISTRY_URL/prompts/{ref}
   (fallback for non-Lambda or local dev registries)
    ↓ (if both fail or are not configured)
3. Local file → {local_dir}/{ref}.txt
    ↓ (if not found)
4. PromptResolutionError raised
```

The direct Lambda invoke path (`PROMPT_REGISTRY_FUNCTION`) is the standard production path. It avoids HTTP overhead and IAM presigning. The HTTP path is useful for local development servers or registries not deployed as Lambda.

## API Routes

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/prompts` | Push new version (always `draft`) |
| `GET` | `/prompts/{id}` | Resolve prompt (query: `version`, `mode`) |
| `GET` | `/prompts/{id}/versions` | List all versions |
| `GET` | `/prompts/{id}/diff?v1=X&v2=Y` | Unified diff |
| `POST` | `/prompts/{id}/promote` | Promote draft → stable (atomic) |
| `POST` | `/prompts/{id}/rollback` | Rollback to previous version |

See [Prompt Registry SDK]({{ '/docs/sdk/prompts' | relative_url }}) for the client API reference.
