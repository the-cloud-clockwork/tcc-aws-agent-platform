---
title: IAM
nav_order: 3
parent: "Identity, Policy & IAM"
---

# IAM: Per-Agent Roles and Least-Privilege Execution

Every agent and the Gateway run under dedicated IAM roles provisioned by the
Terraform modules. This page describes the role structure, trust policies,
permission scope, and how sensitive values like inference API keys are handled
in the deployment model.

## Role Architecture

Three role types exist in a deployed platform:

| Role | Provisioned by | Purpose |
|------|---------------|---------|
| Per-agent execution role | `modules/agents/iam.tf` | Runtime permissions for each individual agent |
| Gateway execution role | `modules/platform/modules/agentcore/gateway.tf` | Routes tool calls to Lambda/Runtime backends |
| AgentCore service role | AWS-managed | Assumed by AgentCore control plane (not managed by these modules) |

## Per-Agent Execution Role

### Trust Policy

Each agent role trusts exactly one service principal: `bedrock-agentcore.amazonaws.com`.
The trust policy adds two conditions that prevent confused-deputy attacks:

```hcl
condition {
  test     = "StringEquals"
  variable = "aws:SourceAccount"
  values   = [data.aws_caller_identity.current.account_id]
}

condition {
  test     = "ArnLike"
  variable = "aws:SourceArn"
  values   = ["arn:aws:bedrock-agentcore:<region>:<account>:*"]
}
```

`aws:SourceAccount` (exact match) ensures the role can only be assumed by
AgentCore acting on behalf of your account — not another account's AgentCore
service. `aws:SourceArn` (prefix match) further restricts to the
bedrock-agentcore ARN namespace in the same account and region.

### Permissions

Permissions are organized as a combination of always-present and conditional
statements. Conditional statements are included only when the corresponding
variable is non-empty, so agents that do not use a feature get no permissions
for it.

#### Always present

| Statement | Actions | Resource scope |
|-----------|---------|---------------|
| `BedrockInvoke` | `bedrock:*` | `*` (required for model invocation; tighten post-launch) |
| `AgentCoreActions` | `bedrock-agentcore:*` | `*` (policy engine, memory, evaluation APIs) |

> **⚠️ Production note:** The `bedrock:*` and `bedrock-agentcore:*` grants on resource `*` above are illustrative placeholders suitable for initial development and experimentation only. Before any production deployment these **must** be replaced with grants scoped to the specific model ARNs your agents invoke (e.g. `arn:aws:bedrock:<region>::foundation-model/<model-id>`) and the specific AgentCore resource ARNs provisioned for your environment. Broad wildcard grants on these namespaces expose your account to unintended model invocations and control-plane operations. Review the [AWS Bedrock IAM reference](https://docs.aws.amazon.com/bedrock/latest/userguide/security-iam.html) when scoping these statements for production.
| `EcrAuth` | `ecr:GetAuthorizationToken` | `*` (ECR API requirement) |
| `EcrPull` | `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer` | Agent's own ECR repository ARN only |
| `CloudWatchLogs` | `logs:CreateLogGroup/Stream/PutLogEvents/Describe*` | Agent-specific log group prefix only |
| `XRayTracing` | `xray:PutTraceSegments`, `xray:PutTelemetryRecords` | `*` (X-Ray API requirement) |
| `EvaluationAndGatewayRoleAccess` | `iam:GetRole`, `iam:PassRole` | `AgentCoreEvalsSDK-*` role pattern + Gateway role ARN |
| `SsmParameterRead` | `ssm:GetParameter`, `ssm:GetParametersByPath` | Platform SSM path prefix only |

#### Conditional (included when the corresponding variable is set)

| Statement | Actions | Condition variable |
|-----------|---------|-------------------|
| `ArtifactsBucketAccess` | `s3:GetObject/PutObject/ListBucket` | `artifacts_bucket_arn != ""` |
| `ExtraS3ReadAccess` | `s3:GetObject/ListBucket` | `extra_s3_read_bucket_arns` non-empty |
| `PlatformKmsDecrypt` | `kms:Decrypt/GenerateDataKey` | `platform_artifacts_kms_key_arn != ""` |
| `DomainKmsDecrypt` | `kms:Decrypt/GenerateDataKey` | `domain_artifacts_kms_key_arn != ""` |
| `StorageKmsAccess` | `kms:Decrypt/GenerateDataKey` | `storage_kms_key_arn != ""` |
| `PromptRegistryInvoke` | `lambda:InvokeFunction` | `prompt_registry_function_arn != ""` |
| `ArtifactsCatalogAccess` | `dynamodb:PutItem` | `artifacts_table_name != ""` |
| `ArtifactsCatalogKMS` | `kms:Encrypt/Decrypt/GenerateDataKey` | `data_kms_key_arn != ""` |
| `IdempotencyTableAccess` | `dynamodb:GetItem/PutItem/DeleteItem` | `idempotency_table_name != ""` |
| `EvaluationTableAccess` | `dynamodb:PutItem/GetItem/Query` | `evaluation_table_name != ""` |


### CloudWatch Log Scope

Log permissions are scoped to agent-specific prefixes, not the entire account:

```
/aws/bedrock-agentcore/<name_prefix>-<agent_key>*
/aws/bedrock-agentcore/runtimes/<agent_key>
```

Adding a new agent via blueprint automatically creates a role with the correct
log group scope for that agent. No manual IAM editing is required.

## Gateway Execution Role

The Gateway role also trusts `bedrock-agentcore.amazonaws.com` with the same
`aws:SourceAccount` + `aws:SourceArn` conditions as agent roles.

Gateway permissions are fully enumerated (no wildcards on bedrock-agentcore
actions) and scoped to specific resource ARN prefixes:

| Statement | Actions | Resource scope |
|-----------|---------|---------------|
| `InvokeMcpLambdaFunctions` | `lambda:InvokeFunction` | Functions matching `<prefix>-<env>-*` only |
| `CloudWatchLogs` | `logs:CreateLogGroup/Stream/PutLogEvents` | Gateway log group prefix only |
| `GatewayRuntimeAccess` | Specific `bedrock-agentcore` Gateway actions | `gateway/*` ARN only |
| `PolicyEngineAccess` | Specific `bedrock-agentcore` policy actions | `policy-engine/*` ARN only |
| `RuntimeAccess` | Get/invoke Runtime | `runtime/*` ARN only |
| `KmsGatewayEncryption` | `kms:Decrypt/Encrypt/GenerateDataKey/DescribeKey` | Specific Gateway KMS key ARN only |

When Cognito is enabled, a separate inline policy adds:

| Statement | Actions | Resource scope |
|-----------|---------|---------------|
| `GetResourceOauth2Token` | `bedrock-agentcore:GetResourceOauth2Token` | Specific OAuth2 credential provider ARN only |

This conditional permission enables the Gateway-to-Runtime M2M token flow
described in [Identity](identity). It is not added when Cognito is disabled.

## KMS Envelope Encryption

The platform provisions five KMS customer-managed keys (CMKs), each with
automatic annual key rotation enabled:

| Key | Alias | Protects |
|-----|-------|---------|
| `data` | `alias/<prefix>-<env>-data` | DynamoDB tables, SQS queues |
| `storage` | `alias/<prefix>-<env>-storage` | S3 buckets (general) |
| `secrets` | `alias/<prefix>-<env>-secrets` | Secrets Manager secrets |
| `platform_artifacts` | `alias/<prefix>-<env>-platform-artifacts` | Platform-tier artifact S3 bucket |
| `domain_artifacts` | `alias/<prefix>-<env>-domain-artifacts` | Domain-tier artifact S3 bucket |

Every key policy grants the root account principal full `kms:*` access, which
means all IAM-scoped key grants (the conditional statements in agent roles
above) flow through standard IAM — the key policy itself does not need
per-principal entries. CloudWatch Logs gets an explicit key policy statement
permitting encryption operations for log delivery, scoped to the account's log
ARN namespace.

Agent roles receive KMS permissions only for the keys they need. An agent
without artifact access gets no KMS Decrypt permission on artifact keys.

## Sensitive Values: Inference API Keys

The platform supports injecting inference provider API keys into agent runtimes
at deployment time. The injection mechanism is direct — the key is passed as a
Terraform variable (`sensitive = true`) and set as a Runtime environment
variable:

```hcl
# modules/agents/variables.tf
variable "litellm_api_key" {
  type      = string
  default   = ""
  sensitive = true  # masked in plan output and state display
}

# modules/agents/runtime.tf — only injected when non-empty
var.litellm_api_key != "" ? { LITELLM_API_KEY = var.litellm_api_key } : {}
```

The same pattern applies to `ANTHROPIC_API_KEY` and Langfuse credentials.

**Security implications to understand:**

- The key value is present in **Terraform state**. Use a backend with
  encryption at rest (S3 + KMS, Terraform Cloud, etc.) and restrict state
  access to the CI role.
- The key is set in the AgentCore **Runtime environment**. It is readable by
  any process running inside the Runtime container. Treat Runtime access
  as equivalent to secret access.
- **Rotation** requires a `terraform apply` with the new key value and a
  Runtime update. Plan for this in your rotation procedures.

For higher-assurance deployments, consider fetching the key from Secrets
Manager inside the agent entrypoint rather than receiving it as an environment
variable:

```python
import boto3, json

def get_inference_key() -> str:
    sm = boto3.client("secretsmanager")
    secret = sm.get_secret_value(SecretId="my-platform/inference-key")
    return json.loads(secret["SecretString"])["api_key"]
```

This keeps the key out of Terraform state and the Runtime environment, at the
cost of a Secrets Manager API call per cold start.

## SSM SecureString: Credential Provider Pre-population

Before running `terraform apply` for any agent that declares API key or OAuth2
credential providers, you must populate the corresponding SSM SecureString
parameters. The Terraform data source reads the parameter value at plan time —
if the parameter is absent, the plan fails.

```bash
# API key provider
aws ssm put-parameter \
  --type SecureString \
  --name "<ssm_root_path>/agents/<agent_id>/credentials/<name>/api-key" \
  --value "..."

# OAuth2 provider — two parameters required
aws ssm put-parameter \
  --type SecureString \
  --name "<ssm_root_path>/agents/<agent_id>/oauth/<name>/client-id" \
  --value "..."

aws ssm put-parameter \
  --type SecureString \
  --name "<ssm_root_path>/agents/<agent_id>/oauth/<name>/client-secret" \
  --value "..."
```

SSM SecureString parameters are encrypted at rest using KMS. Use the platform's
`secrets` KMS key (`alias/<prefix>-<env>-secrets`) for consistency:

```bash
aws ssm put-parameter \
  --type SecureString \
  --key-id "alias/<prefix>-<env>-secrets" \
  --name "..." \
  --value "..."
```

## Deployment Order and Role Dependencies

The agents module depends on platform module outputs for role construction. The
`gateway_role_arn` output from the platform module is passed to the agents
module so the per-agent `EvaluationAndGatewayRoleAccess` statement can scope
`iam:PassRole` to the correct Gateway role ARN. Deploy in order:

```
platform module → agents module → workflows module
```

Attempting to deploy the agents module before the platform module fails because
the Gateway role ARN and KMS key ARNs are not yet available.

## See Also

- [Identity](identity) — the auth patterns built on top of these IAM roles
- [Cedar Policy](cedar-policy) — access control at the tool-call layer
- [Infrastructure: Agents Module](../infrastructure/agents-module) — full variable reference for IAM configuration
- [Infrastructure: Platform Module](../infrastructure/platform-module) — KMS key and role outputs
