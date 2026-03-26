# ──────────────────────────────────────────────────────────────────────────────
# AgentCore Sub-Module -- Gateway
#
# Creates the AgentCore Gateway (MCP protocol) with an IAM execution role.
# The Gateway routes tool calls from agents to MCP servers registered as
# Gateway targets.
#
# Authorizer type is configurable: AWS_IAM (default) or CUSTOM_JWT (Cognito
# or external OIDC provider).
# ──────────────────────────────────────────────────────────────────────────────

locals {
  prefix = var.resource_prefix
  env    = var.environment
}

# ── IAM Role: Gateway Execution ──────────────────────────────────────────────

data "aws_iam_policy_document" "gateway_trust" {
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
      values   = [var.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:bedrock-agentcore:${var.aws_region}:${var.account_id}:*"]
    }
  }
}

resource "aws_iam_role" "gateway" {
  name               = "${local.prefix}-${local.env}-gateway"
  assume_role_policy = data.aws_iam_policy_document.gateway_trust.json

  tags = merge(var.tags, {
    Name      = "${local.prefix}-${local.env}-gateway"
    Module    = "agentcore"
    Component = "gateway"
  })
}

data "aws_iam_policy_document" "gateway_permissions" {
  # Allow invoking Lambda functions that serve as MCP server backends
  statement {
    sid    = "InvokeMcpLambdaFunctions"
    effect = "Allow"
    actions = [
      "lambda:InvokeFunction",
    ]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${var.account_id}:function:${local.prefix}-${local.env}-*",
    ]
  }

  # Allow writing logs to CloudWatch
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/bedrock-agentcore/${local.prefix}-${local.env}-*",
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/bedrock-agentcore/${local.prefix}-${local.env}-*:*",
    ]
  }

  # Allow Gateway to read policy engines for policy enforcement
  statement {
    sid    = "PolicyEngineAccess"
    effect = "Allow"
    actions = [
      "bedrock-agentcore:GetPolicyEngine",
      "bedrock-agentcore:CheckAuthorizePermissions",
    ]
    resources = [
      "arn:aws:bedrock-agentcore:${var.aws_region}:${var.account_id}:policy-engine/*",
    ]
  }

  # Allow KMS operations for gateway encryption
  statement {
    sid    = "KmsGatewayEncryption"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey",
      "kms:DescribeKey",
    ]
    resources = [
      var.gateway_kms_key_arn != "" ? var.gateway_kms_key_arn : "*",
    ]
  }
}

resource "aws_iam_role_policy" "gateway" {
  name   = "${local.prefix}-${local.env}-gateway-policy"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway_permissions.json
}

# ── OAuth2 Token Retrieval Permissions (conditional on Cognito) ─────────────

data "aws_iam_policy_document" "gateway_oauth2" {
  count = var.cognito_enabled ? 1 : 0

  statement {
    sid    = "GetResourceOauth2Token"
    effect = "Allow"
    actions = [
      "bedrock-agentcore:GetResourceOauth2Token",
    ]
    resources = [
      aws_bedrockagentcore_oauth2_credential_provider.gateway_mcp[0].credential_provider_arn,
    ]
  }
}

resource "aws_iam_role_policy" "gateway_oauth2" {
  count = var.cognito_enabled ? 1 : 0

  name   = "${local.prefix}-${local.env}-gateway-oauth2-policy"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway_oauth2[0].json
}

# ── AgentCore Gateway ────────────────────────────────────────────────────────

resource "aws_bedrockagentcore_gateway" "this" {
  name          = "${local.prefix}-${local.env}-gateway"
  protocol_type = "MCP"
  role_arn      = aws_iam_role.gateway.arn

  authorizer_type = var.gateway_auth_type

  # CUSTOM_JWT authorizer configuration -- only included when auth type is CUSTOM_JWT
  dynamic "authorizer_configuration" {
    for_each = var.gateway_auth_type == "CUSTOM_JWT" ? [1] : []
    content {
      custom_jwt_authorizer {
        discovery_url   = var.gateway_jwt_discovery_url
        allowed_clients = var.gateway_jwt_allowed_clients
      }
    }
  }

  kms_key_arn = var.gateway_kms_key_arn != "" ? var.gateway_kms_key_arn : null

  tags = merge(var.tags, {
    Name      = "${local.prefix}-${local.env}-gateway"
    Module    = "agentcore"
    Component = "gateway"
  })
}
