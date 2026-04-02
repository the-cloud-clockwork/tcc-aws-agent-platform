# ──────────────────────────────────────────────────────────────────────────────
# Security Sub-Module -- Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "resource_prefix" {
  description = "Prefix for all resource names (e.g. 'platform')."
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, production)."
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources created by this module."
  type        = map(string)
  default     = {}
}

# ── KMS ──────────────────────────────────────────────────────────────────────

variable "kms_key_deletion_window_days" {
  description = "Number of days before a KMS key is permanently deleted after scheduling."
  type        = number
  default     = 30

  validation {
    condition     = var.kms_key_deletion_window_days >= 7 && var.kms_key_deletion_window_days <= 30
    error_message = "KMS key deletion window must be between 7 and 30 days."
  }
}

# ── WAF ──────────────────────────────────────────────────────────────────────

variable "waf_enabled" {
  description = "Whether to create the WAF Web ACL and associated rules."
  type        = bool
}

variable "waf_rate_limit" {
  description = "Maximum requests per 5-minute window per IP before rate limiting."
  type        = number
  default     = 1000
}

variable "waf_ip_whitelist" {
  description = "List of CIDR blocks to whitelist in WAF (e.g. ['203.0.113.0/24']). Empty list disables the IP whitelist rule."
  type        = list(string)
  default     = []
}
