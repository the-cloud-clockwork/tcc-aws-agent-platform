# ──────────────────────────────────────────────────────────────────────────────
# AgentCore Sub-Module — Variables
#
# Inputs for Gateway, Memory, builtin tools, and Cognito resources.
# ──────────────────────────────────────────────────────────────────────────────

# ── Common ───────────────────────────────────────────────────────────────────

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
  description = "AWS account ID, used in IAM trust policies and resource ARN scoping."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be a 12-digit AWS account ID."
  }
}

variable "aws_region" {
  description = "AWS region for resource ARN construction."
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources created by this module."
  type        = map(string)
  default     = {}
}

# ── Gateway ──────────────────────────────────────────────────────────────────

variable "gateway_auth_type" {
  description = "Authorizer type for the AgentCore Gateway. One of: AWS_IAM, CUSTOM_JWT."
  type        = string

  validation {
    condition     = contains(["AWS_IAM", "CUSTOM_JWT"], var.gateway_auth_type)
    error_message = "gateway_auth_type must be AWS_IAM or CUSTOM_JWT."
  }
}

variable "gateway_jwt_discovery_url" {
  description = "OIDC discovery URL for CUSTOM_JWT authorizer. Required when gateway_auth_type is CUSTOM_JWT."
  type        = string
  default     = ""
}

variable "gateway_jwt_allowed_clients" {
  description = "List of allowed client IDs for CUSTOM_JWT authorizer. Required when gateway_auth_type is CUSTOM_JWT."
  type        = list(string)
  default     = []
}

# ── Memory ───────────────────────────────────────────────────────────────────

variable "memory_event_expiry_days" {
  description = "Number of days before memory events expire."
  type        = number

  validation {
    condition     = var.memory_event_expiry_days >= 1
    error_message = "memory_event_expiry_days must be at least 1."
  }
}

variable "memory_kms_key_arn" {
  description = "ARN of the KMS key used to encrypt AgentCore Memory data. Empty string to use AWS-managed key."
  type        = string
  default     = ""
}

# ── Cognito ──────────────────────────────────────────────────────────────────

variable "cognito_enabled" {
  description = "Whether to create a Cognito user pool for agent authentication."
  type        = bool
  default     = false
}

# ── Builtin Tools ────────────────────────────────────────────────────────────

variable "code_interpreter_enabled" {
  description = "Whether to create the AgentCore Code Interpreter builtin tool."
  type        = bool
  default     = false
}

variable "browser_enabled" {
  description = "Whether to create the AgentCore Browser builtin tool."
  type        = bool
  default     = false
}
