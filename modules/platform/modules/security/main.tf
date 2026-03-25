# ──────────────────────────────────────────────────────────────────────────────
# Security Sub-Module -- KMS Keys & Secrets Manager
#
# Replaces the CDK SecurityStack. Creates envelope-encryption keys for every
# data tier and a Secrets Manager secret for the observability API key.
# ──────────────────────────────────────────────────────────────────────────────

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  prefix     = var.resource_prefix
  env        = var.environment
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name

  # Standard key policy: grant full access to the root account so that IAM
  # policies can further delegate permissions to roles and users.
  key_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnableRootAccountAccess"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${local.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid    = "AllowCloudWatchLogs"
        Effect = "Allow"
        Principal = { Service = "logs.${local.region}.amazonaws.com" }
        Action = [
          "kms:Encrypt*",
          "kms:Decrypt*",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:Describe*"
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${local.region}:${local.account_id}:*"
          }
        }
      }
    ]
  })
}

# ── KMS Key 1: Data (DynamoDB / SQS) ────────────────────────────────────────

resource "aws_kms_key" "data" {
  description             = "${local.prefix}-${local.env} data encryption key (DynamoDB, SQS)"
  deletion_window_in_days = var.kms_key_deletion_window_days
  enable_key_rotation     = true
  policy                  = local.key_policy
  tags                    = var.tags
}

resource "aws_kms_alias" "data" {
  name          = "alias/${local.prefix}-${local.env}-data"
  target_key_id = aws_kms_key.data.key_id
}

# ── KMS Key 2: Storage (S3 general) ─────────────────────────────────────────

resource "aws_kms_key" "storage" {
  description             = "${local.prefix}-${local.env} storage encryption key (S3)"
  deletion_window_in_days = var.kms_key_deletion_window_days
  enable_key_rotation     = true
  policy                  = local.key_policy
  tags                    = var.tags
}

resource "aws_kms_alias" "storage" {
  name          = "alias/${local.prefix}-${local.env}-storage"
  target_key_id = aws_kms_key.storage.key_id
}

# ── KMS Key 3: Secrets (Secrets Manager) ─────────────────────────────────────

resource "aws_kms_key" "secrets" {
  description             = "${local.prefix}-${local.env} secrets encryption key (Secrets Manager)"
  deletion_window_in_days = var.kms_key_deletion_window_days
  enable_key_rotation     = true
  policy                  = local.key_policy
  tags                    = var.tags
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${local.prefix}-${local.env}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

# ── KMS Key 4: Platform Artifacts ────────────────────────────────────────────

resource "aws_kms_key" "platform_artifacts" {
  description             = "${local.prefix}-${local.env} platform-tier artifact encryption key"
  deletion_window_in_days = var.kms_key_deletion_window_days
  enable_key_rotation     = true
  policy                  = local.key_policy
  tags                    = var.tags
}

resource "aws_kms_alias" "platform_artifacts" {
  name          = "alias/${local.prefix}-${local.env}-platform-artifacts"
  target_key_id = aws_kms_key.platform_artifacts.key_id
}

# ── KMS Key 5: Domain Artifacts ──────────────────────────────────────────────

resource "aws_kms_key" "domain_artifacts" {
  description             = "${local.prefix}-${local.env} domain-tier artifact encryption key"
  deletion_window_in_days = var.kms_key_deletion_window_days
  enable_key_rotation     = true
  policy                  = local.key_policy
  tags                    = var.tags
}

resource "aws_kms_alias" "domain_artifacts" {
  name          = "alias/${local.prefix}-${local.env}-domain-artifacts"
  target_key_id = aws_kms_key.domain_artifacts.key_id
}

# ── Secrets Manager: Observability API Key ───────────────────────────────────

resource "aws_secretsmanager_secret" "observability_api_key" {
  name        = "${local.prefix}/${local.env}/observability-api-key"
  description = "API key for the observability provider (e.g. Langfuse)"
  kms_key_id  = aws_kms_key.secrets.arn
  tags        = var.tags
}
