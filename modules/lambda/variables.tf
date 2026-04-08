variable "function_name" {
  description = "Lambda function name (without prefix)."
  type        = string
}

variable "source_dir" {
  description = "Path to the Lambda source directory to zip."
  type        = string
}

variable "handler" {
  description = "Lambda handler entry point."
  type        = string
  default     = "handler.handler"
}

variable "runtime" {
  description = "Lambda runtime identifier."
  type        = string
  default     = "python3.12"
}

variable "memory_size" {
  description = "Lambda memory in MB."
  type        = number
  default     = 256
}

variable "timeout" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 30
}

variable "architectures" {
  description = "Lambda instruction set architectures."
  type        = list(string)
  default     = ["arm64"]
}

variable "environment_variables" {
  description = "Environment variables for the Lambda function."
  type        = map(string)
  default     = {}
}

variable "vpc_enabled" {
  description = "Whether to attach the Lambda to a VPC."
  type        = bool
  default     = false
}

variable "subnet_ids" {
  description = "Subnet IDs for VPC-attached Lambda. Required when vpc_enabled is true."
  type        = list(string)
  default     = []
}

variable "security_group_ids" {
  description = "Security group IDs for VPC-attached Lambda. Required when vpc_enabled is true."
  type        = list(string)
  default     = []
}

variable "kms_key_arn" {
  description = "KMS key ARN for log group encryption. Empty uses AWS-managed key."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days."
  type        = number
  default     = 14
}

variable "resource_prefix" {
  description = "Prefix for all resource names."
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default     = {}
}

variable "additional_policies" {
  description = "List of IAM policy JSON documents to attach as inline policies."
  type        = list(string)
  default     = []
}
