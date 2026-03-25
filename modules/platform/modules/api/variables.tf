# ──────────────────────────────────────────────────────────────────────────────
# API Sub-Module -- Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "resource_prefix" {
  description = "Prefix for all resource names (e.g. 'platform')"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, production)"
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}

# ── Data dependencies ────────────────────────────────────────────────────────

variable "artifacts_table_name" {
  description = "DynamoDB artifacts table name"
  type        = string
}

variable "artifacts_table_arn" {
  description = "DynamoDB artifacts table ARN"
  type        = string
}

variable "artifacts_bucket_name" {
  description = "S3 artifacts bucket name"
  type        = string
}

variable "artifacts_bucket_arn" {
  description = "S3 artifacts bucket ARN"
  type        = string
}

# ── KMS keys ─────────────────────────────────────────────────────────────────

variable "platform_artifacts_kms_key_arn" {
  description = "KMS key ARN for platform artifact encryption/decryption"
  type        = string
}

variable "domain_artifacts_kms_key_arn" {
  description = "KMS key ARN for domain artifact encryption/decryption"
  type        = string
}

variable "data_kms_key_arn" {
  description = "KMS key ARN for DynamoDB table encryption (data-at-rest)"
  type        = string
}

# ── API Gateway settings ─────────────────────────────────────────────────────

variable "api_throttle_rate" {
  description = "API Gateway throttle rate limit (requests per second)"
  type        = number
}

variable "api_throttle_burst" {
  description = "API Gateway throttle burst limit"
  type        = number
}

variable "api_cors_origins" {
  description = "Allowed CORS origins for API Gateway"
  type        = list(string)
}

# ── WAF (conditional) ───────────────────────────────────────────────────────

variable "waf_acl_arn" {
  description = "WAF Web ACL ARN for API Gateway association. Empty string disables association."
  type        = string
  default     = ""
}

variable "waf_enabled" {
  description = "Whether WAF is enabled. Controls WAF-to-API Gateway association."
  type        = bool
  default     = false
}

# ── SQS (artifact notifications) ──────────────────────────────────────────

variable "artifact_queue_url" {
  description = "SQS queue URL for artifact status-change notifications"
  type        = string
}

variable "artifact_queue_arn" {
  description = "SQS queue ARN for artifact status-change notifications"
  type        = string
}
