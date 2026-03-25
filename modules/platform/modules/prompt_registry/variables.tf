# ──────────────────────────────────────────────────────────────────────────────
# Prompt Registry Sub-Module — Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "resource_prefix" {
  type = string
}

variable "environment" {
  type = string
}

variable "prompt_table_name" {
  type        = string
  description = "DynamoDB table name for prompt metadata."
}

variable "prompt_table_arn" {
  type        = string
  description = "DynamoDB table ARN for IAM policy."
}

variable "prompt_bucket_name" {
  type        = string
  description = "S3 bucket name for prompt content."
}

variable "prompt_bucket_arn" {
  type        = string
  description = "S3 bucket ARN for IAM policy."
}

variable "storage_kms_key_arn" {
  type        = string
  description = "KMS key ARN for S3 server-side encryption."
  default     = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "data_kms_key_arn" {
  type        = string
  description = "KMS key ARN for DynamoDB table encryption."
  default     = ""
}
