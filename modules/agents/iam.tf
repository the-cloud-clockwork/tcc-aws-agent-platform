# ──────────────────────────────────────────────────────────────────────────────
# Agents Module -- IAM
#
# Per-agent IAM roles with trust policy for bedrock-agentcore.amazonaws.com.
# Each agent gets its own role scoped to the minimum permissions it needs:
# Bedrock model invocation, ECR image pull, CloudWatch logs, X-Ray tracing,
# SSM parameter reads, and conditional artifact storage access.
# ──────────────────────────────────────────────────────────────────────────────

# ── Trust Policy (shared template) ─────────────────────────────────────────

data "aws_iam_policy_document" "agent_trust" {
  for_each = local.blueprints

  statement {
    sid     = "AllowBedrockAgentCoreAssume"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values = [
        "arn:aws:bedrock-agentcore:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*"
      ]
    }
  }
}

# ── Per-Agent IAM Role ─────────────────────────────────────────────────────

resource "aws_iam_role" "agent" {
  for_each = local.blueprints

  name               = "${local.name_prefix}-agent-${each.key}-role"
  assume_role_policy = data.aws_iam_policy_document.agent_trust[each.key].json

  tags = merge(local.tags, {
    Name      = "${local.name_prefix}-agent-${each.key}-role"
    Component = "agent"
    AgentId   = each.key
  })
}

# ── Per-Agent Permissions Policy ───────────────────────────────────────────

data "aws_iam_policy_document" "agent_permissions" {
  for_each = local.blueprints

  # Bedrock model invocation -- scoped to agent's configured model
  statement {
    sid    = "BedrockInvoke"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = [
      "arn:aws:bedrock:${var.bedrock_region != "" ? var.bedrock_region : data.aws_region.current.name}::foundation-model/${try(each.value.model.model_id, "*")}",
    ]
  }

  # ECR auth token -- must be wildcard per API requirement
  statement {
    sid       = "EcrAuth"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  # ECR image pull -- scoped to agent's repository
  statement {
    sid    = "EcrPull"
    effect = "Allow"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.agent[each.key].arn]
  }

  # CloudWatch Logs -- scoped to agent-specific log groups
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
    ]
    resources = [
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/${local.name_prefix}-${each.key}*",
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/${local.name_prefix}-${each.key}*:*",
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/${each.key}",
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/${each.key}:*",
    ]
  }

  # X-Ray tracing
  statement {
    sid    = "XRayTracing"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
    ]
    resources = ["*"]
  }

  # SSM parameter reads scoped to platform path
  statement {
    sid    = "SsmParameterRead"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParametersByPath",
    ]
    resources = [
      "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_root_path}/*"
    ]
  }

  # Conditional: S3 artifact access (only when bucket is provided)
  dynamic "statement" {
    for_each = var.artifacts_bucket_arn != "" ? [1] : []
    content {
      sid    = "ArtifactsBucketAccess"
      effect = "Allow"
      actions = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket",
      ]
      resources = [
        var.artifacts_bucket_arn,
        "${var.artifacts_bucket_arn}/*",
      ]
    }
  }

  # Conditional: KMS decrypt for platform artifacts key
  dynamic "statement" {
    for_each = var.platform_artifacts_kms_key_arn != "" ? [1] : []
    content {
      sid    = "PlatformKmsDecrypt"
      effect = "Allow"
      actions = [
        "kms:Decrypt",
        "kms:GenerateDataKey",
      ]
      resources = [var.platform_artifacts_kms_key_arn]
    }
  }

  # Conditional: KMS decrypt for domain artifacts key
  dynamic "statement" {
    for_each = var.domain_artifacts_kms_key_arn != "" ? [1] : []
    content {
      sid    = "DomainKmsDecrypt"
      effect = "Allow"
      actions = [
        "kms:Decrypt",
        "kms:GenerateDataKey",
      ]
      resources = [var.domain_artifacts_kms_key_arn]
    }
  }

  # Conditional: KMS access for storage key (ECR encryption)
  dynamic "statement" {
    for_each = var.storage_kms_key_arn != "" ? [1] : []
    content {
      sid    = "StorageKmsAccess"
      effect = "Allow"
      actions = [
        "kms:Decrypt",
        "kms:GenerateDataKey",
      ]
      resources = [var.storage_kms_key_arn]
    }
  }

  # Conditional: Prompt Registry Lambda Function URL invocation
  dynamic "statement" {
    for_each = var.prompt_registry_function_arn != "" ? [1] : []
    content {
      sid    = "PromptRegistryInvoke"
      effect = "Allow"
      actions = [
        "lambda:InvokeFunction",
      ]
      resources = [var.prompt_registry_function_arn]
    }
  }

  # Conditional: DynamoDB idempotency table access
  dynamic "statement" {
    for_each = var.idempotency_table_name != "" ? [1] : []
    content {
      sid    = "IdempotencyTableAccess"
      effect = "Allow"
      actions = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:DeleteItem",
      ]
      resources = [
        "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${var.idempotency_table_name}",
      ]
    }
  }
}

resource "aws_iam_role_policy" "agent" {
  for_each = local.blueprints

  name   = "${local.name_prefix}-agent-${each.key}-policy"
  role   = aws_iam_role.agent[each.key].id
  policy = data.aws_iam_policy_document.agent_permissions[each.key].json
}
