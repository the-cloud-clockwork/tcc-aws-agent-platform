# ──────────────────────────────────────────────────────────────────────────────
# Data Sub-Module — Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "resource_prefix" {
  description = "Prefix for all resource names (e.g. 'platform')."
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, production)."
  type        = string

  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be one of: dev, staging, production."
  }
}

variable "account_id" {
  description = "AWS account ID, used in bucket naming and bucket policies."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be a 12-digit AWS account ID."
  }
}

variable "tags" {
  description = "Tags applied to all resources created by this module."
  type        = map(string)
  default     = {}
}

# ── KMS ──────────────────────────────────────────────────────────────────────

variable "data_kms_key_arn" {
  description = "ARN of the KMS key used to encrypt DynamoDB tables and SQS queues."
  type        = string

  validation {
    condition     = can(regex("^arn:aws:kms:", var.data_kms_key_arn))
    error_message = "data_kms_key_arn must be a valid KMS key ARN."
  }
}

variable "storage_kms_key_arn" {
  description = "ARN of the KMS key used for S3 bucket server-side encryption."
  type        = string

  validation {
    condition     = can(regex("^arn:aws:kms:", var.storage_kms_key_arn))
    error_message = "storage_kms_key_arn must be a valid KMS key ARN."
  }
}

variable "platform_artifacts_kms_key_arn" {
  description = "ARN of the KMS key required for writes to /platform/* in the artifacts bucket."
  type        = string

  validation {
    condition     = can(regex("^arn:aws:kms:", var.platform_artifacts_kms_key_arn))
    error_message = "platform_artifacts_kms_key_arn must be a valid KMS key ARN."
  }
}

variable "domain_artifacts_kms_key_arn" {
  description = "ARN of the KMS key required for writes to /domain/* in the artifacts bucket."
  type        = string

  validation {
    condition     = can(regex("^arn:aws:kms:", var.domain_artifacts_kms_key_arn))
    error_message = "domain_artifacts_kms_key_arn must be a valid KMS key ARN."
  }
}

# ── DynamoDB ─────────────────────────────────────────────────────────────────

variable "dynamodb_billing_mode" {
  description = "DynamoDB billing mode: PAY_PER_REQUEST (dev) or PROVISIONED (staging/production)."
  type        = string
  default     = "PAY_PER_REQUEST"

  validation {
    condition     = contains(["PAY_PER_REQUEST", "PROVISIONED"], var.dynamodb_billing_mode)
    error_message = "dynamodb_billing_mode must be PAY_PER_REQUEST or PROVISIONED."
  }
}

variable "dynamodb_read_capacity" {
  description = "Provisioned read capacity units (only used when billing mode is PROVISIONED)."
  type        = number
  default     = 5

  validation {
    condition     = var.dynamodb_read_capacity >= 1
    error_message = "dynamodb_read_capacity must be at least 1."
  }
}

variable "dynamodb_write_capacity" {
  description = "Provisioned write capacity units (only used when billing mode is PROVISIONED)."
  type        = number
  default     = 5

  validation {
    condition     = var.dynamodb_write_capacity >= 1
    error_message = "dynamodb_write_capacity must be at least 1."
  }
}

# ── CloudFront ───────────────────────────────────────────────────────────────

variable "cloudfront_enabled" {
  description = "Whether to create a CloudFront distribution for the artifacts bucket."
  type        = bool
  default     = false
}

variable "waf_acl_arn" {
  description = "ARN of the WAF Web ACL to associate with CloudFront. Empty string disables WAF association."
  type        = string
  default     = ""
}

# ── Lifecycle ────────────────────────────────────────────────────────────────

variable "removal_policy_destroy" {
  description = "If true, allow deletion of DynamoDB tables and S3 buckets on terraform destroy. Use only in dev."
  type        = bool
  default     = false
}
