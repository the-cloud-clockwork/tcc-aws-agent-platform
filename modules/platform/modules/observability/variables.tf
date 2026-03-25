# ──────────────────────────────────────────────────────────────────────────────
# Observability Sub-Module -- Variables
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

variable "log_retention_days" {
  description = "CloudWatch log group retention in days"
  type        = number
}

variable "sns_alert_email" {
  description = "Email address for SNS alert subscription. Empty string disables the subscription."
  type        = string
  default     = ""
}

variable "kms_key_arn" {
  description = "Optional KMS key ARN for SNS topic encryption. Empty string disables encryption."
  type        = string
  default     = ""
}

variable "enable_transaction_search" {
  description = "Create CloudWatch Logs resource policy for X-Ray Transaction Search (GenAI Observability)."
  type        = bool
  default     = true
}
