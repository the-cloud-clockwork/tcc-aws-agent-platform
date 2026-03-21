# ──────────────────────────────────────────────────────────────────────────────
# Data Sub-Module — S3 Buckets
#
# Three buckets:
#   1. artifacts     — Two-tier bucket with /platform and /domain paths,
#                      each enforcing a distinct KMS key via bucket policy.
#   2. prompt-registry — Versioned prompt content storage.
#   3. historical-data — Historical data (read-heavy workloads).
#
# Naming: {prefix}-{env}-{name}-{account_id}
# ──────────────────────────────────────────────────────────────────────────────

locals {
  bucket_names = {
    artifacts       = "${var.resource_prefix}-${var.environment}-artifacts-${var.account_id}"
    prompt_registry = "${var.resource_prefix}-${var.environment}-prompt-registry-${var.account_id}"
    historical_data = "${var.resource_prefix}-${var.environment}-historical-data-${var.account_id}"
  }
}

# ═════════════════════════════════════════════════════════════════════════════
# 1. Artifacts Bucket — Two-Tier KMS Enforcement
# ═════════════════════════════════════════════════════════════════════════════

resource "aws_s3_bucket" "artifacts" {
  bucket        = local.bucket_names.artifacts
  force_destroy = var.removal_policy_destroy

  tags = merge(var.tags, {
    Name      = local.bucket_names.artifacts
    Module    = "data"
    Component = "s3"
    Role      = "artifacts"
  })
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.storage_kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
  }

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = 365
    }
  }
}

# ── Two-Tier Bucket Policy ──────────────────────────────────────────────────
#
# CRITICAL: This enforces the platform security model.
#   - /platform/* objects MUST be encrypted with platform_artifacts_kms_key_arn
#   - /domain/*   objects MUST be encrypted with domain_artifacts_kms_key_arn
#   - CloudFront OAC read access (conditional on cloudfront_enabled)
# ──────────────────────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "artifacts_bucket_policy" {
  # ── DENY: PutObject to /platform/* without the platform KMS key ──────────
  statement {
    sid    = "DenyPlatformWritesWithoutPlatformKMSKey"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:PutObject"]

    resources = ["${aws_s3_bucket.artifacts.arn}/platform/*"]

    # Deny when the encryption header does NOT match the platform KMS key
    condition {
      test     = "StringNotEqualsIfExists"
      variable = "s3:x-amz-server-side-encryption-aws-kms-key-id"
      values   = [var.platform_artifacts_kms_key_arn]
    }
  }

  # ── DENY: PutObject to /domain/* without the domain KMS key ──────────────
  statement {
    sid    = "DenyDomainWritesWithoutDomainKMSKey"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:PutObject"]

    resources = ["${aws_s3_bucket.artifacts.arn}/domain/*"]

    # Deny when the encryption header does NOT match the domain KMS key
    condition {
      test     = "StringNotEqualsIfExists"
      variable = "s3:x-amz-server-side-encryption-aws-kms-key-id"
      values   = [var.domain_artifacts_kms_key_arn]
    }
  }

  # ── ALLOW: CloudFront OAC read access (conditional) ──────────────────────
  dynamic "statement" {
    for_each = var.cloudfront_enabled ? [1] : []
    content {
      sid    = "AllowCloudFrontOACRead"
      effect = "Allow"

      principals {
        type        = "Service"
        identifiers = ["cloudfront.amazonaws.com"]
      }

      actions = ["s3:GetObject"]

      resources = ["${aws_s3_bucket.artifacts.arn}/*"]

      condition {
        test     = "StringEquals"
        variable = "AWS:SourceArn"
        values   = [aws_cloudfront_distribution.artifacts[0].arn]
      }
    }
  }
}

resource "aws_s3_bucket_policy" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  policy = data.aws_iam_policy_document.artifacts_bucket_policy.json
}

# ═════════════════════════════════════════════════════════════════════════════
# 2. Prompt Registry Bucket
# ═════════════════════════════════════════════════════════════════════════════

resource "aws_s3_bucket" "prompt_registry" {
  bucket        = local.bucket_names.prompt_registry
  force_destroy = var.removal_policy_destroy

  tags = merge(var.tags, {
    Name      = local.bucket_names.prompt_registry
    Module    = "data"
    Component = "s3"
    Role      = "prompt-registry"
  })
}

resource "aws_s3_bucket_versioning" "prompt_registry" {
  bucket = aws_s3_bucket.prompt_registry.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "prompt_registry" {
  bucket = aws_s3_bucket.prompt_registry.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "prompt_registry" {
  bucket = aws_s3_bucket.prompt_registry.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.storage_kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "prompt_registry" {
  bucket = aws_s3_bucket.prompt_registry.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = 180
    }
  }
}

# ═════════════════════════════════════════════════════════════════════════════
# 3. Historical Data Bucket
# ═════════════════════════════════════════════════════════════════════════════

resource "aws_s3_bucket" "historical_data" {
  bucket        = local.bucket_names.historical_data
  force_destroy = var.removal_policy_destroy

  tags = merge(var.tags, {
    Name      = local.bucket_names.historical_data
    Module    = "data"
    Component = "s3"
    Role      = "historical-data"
  })
}

resource "aws_s3_bucket_versioning" "historical_data" {
  bucket = aws_s3_bucket.historical_data.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "historical_data" {
  bucket = aws_s3_bucket.historical_data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "historical_data" {
  bucket = aws_s3_bucket.historical_data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.storage_kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "historical_data" {
  bucket = aws_s3_bucket.historical_data.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 180
      storage_class = "GLACIER"
    }
  }

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = 365
    }
  }
}
