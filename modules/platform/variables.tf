## -----------------------------------------------------
## Platform Module -- Top-Level Variables
## Domain repos set these when consuming the module.
## -----------------------------------------------------

variable "environment" {
  type        = string
  description = "Deployment environment: dev, staging, production"
  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Must be dev, staging, or production."
  }
}

variable "resource_prefix" {
  type        = string
  description = "Prefix for all resource names (e.g. 'platform')"
}

variable "aws_region" {
  type        = string
  description = "Primary AWS region for deployment"
}

variable "bedrock_region" {
  type        = string
  description = "Region for Bedrock model access (may differ from primary)"
}

variable "ssm_root_path" {
  type        = string
  description = "Root SSM parameter path (e.g. /platform/dev)"
}

# -- Network ---------------------------------------------------------

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "availability_zones" {
  type    = list(string)
  default = []
}

variable "nat_gateway_count" {
  type    = number
  default = 1
}

# -- Security --------------------------------------------------------

variable "kms_key_deletion_window_days" {
  type    = number
  default = 30
}

variable "waf_enabled" {
  type    = bool
  default = false
}

variable "waf_rate_limit" {
  type    = number
  default = 1000
}

variable "waf_ip_whitelist" {
  type    = list(string)
  default = []
}

# -- Data ------------------------------------------------------------

variable "dynamodb_billing_mode" {
  type    = string
  default = "PAY_PER_REQUEST"
  validation {
    condition     = contains(["PAY_PER_REQUEST", "PROVISIONED"], var.dynamodb_billing_mode)
    error_message = "Must be PAY_PER_REQUEST or PROVISIONED."
  }
}

variable "dynamodb_read_capacity" {
  type    = number
  default = 25
}

variable "dynamodb_write_capacity" {
  type    = number
  default = 10
}

variable "cloudfront_enabled" {
  type    = bool
  default = true
}

variable "removal_policy_destroy" {
  type        = bool
  description = "true for dev (destroy on removal), false for staging/production (retain)"
  default     = true
}

# -- AgentCore -------------------------------------------------------

variable "gateway_auth_type" {
  type    = string
  default = "AWS_IAM"
  validation {
    condition     = contains(["AWS_IAM", "CUSTOM_JWT", "NONE"], var.gateway_auth_type)
    error_message = "Must be AWS_IAM, CUSTOM_JWT, or NONE."
  }
}

variable "gateway_jwt_discovery_url" {
  type    = string
  default = ""
}

variable "gateway_jwt_allowed_clients" {
  type    = list(string)
  default = []
}

variable "memory_event_expiry_days" {
  type    = number
  default = 30
}

variable "memory_description" {
  type        = string
  description = "Description for the AgentCore Memory resource"
  default     = ""
}

variable "cognito_enabled" {
  type    = bool
  default = false
}

variable "builtin_browser_enabled" {
  type    = bool
  default = false
}

variable "builtin_code_interpreter_enabled" {
  type    = bool
  default = false
}

# -- Observability ---------------------------------------------------

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "sns_alert_email" {
  type    = string
  default = ""
}

# -- API -------------------------------------------------------------

variable "api_throttle_rate" {
  type    = number
  default = 100
}

variable "api_throttle_burst" {
  type    = number
  default = 200
}

variable "api_cors_origins" {
  type    = list(string)
  default = []
}

# -- Tags ------------------------------------------------------------

variable "tags" {
  type    = map(string)
  default = {}
}
