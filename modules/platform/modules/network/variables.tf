## -----------------------------------------------------
## Network Sub-Module — Variables
## -----------------------------------------------------

variable "resource_prefix" {
  type        = string
  description = "Prefix for all resource names (e.g. 'platform-dev')"
}

variable "environment" {
  type        = string
  description = "Deployment environment: dev, staging, production"
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for the VPC"
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr must be a valid CIDR block."
  }
}

variable "availability_zones" {
  type        = list(string)
  description = "List of AZs to deploy into. If empty, auto-discovers available AZs in the current region."
  default     = []
}

variable "nat_gateway_count" {
  type        = number
  description = "Number of NAT Gateways (1 for dev, match AZ count for HA in production)"
  default     = 1

  validation {
    condition     = var.nat_gateway_count >= 1
    error_message = "At least one NAT Gateway is required for private subnet egress."
  }
}

variable "tags" {
  type        = map(string)
  description = "Additional tags to apply to all resources"
  default     = {}
}
