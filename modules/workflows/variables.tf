## -----------------------------------------------------
## Workflows Module -- Variables
## Reads workflow YAML and creates Step Functions.
## -----------------------------------------------------

variable "environment" {
  type = string
}

variable "resource_prefix" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "ssm_root_path" {
  type = string
}

variable "workflow_dir" {
  type        = string
  description = "Path to directory containing workflow blueprint YAML files"
}

variable "agent_runtime_arns" {
  type        = map(string)
  description = "Map of agent_id → Runtime ARN for task invocations"
  default     = {}
}

variable "lambda_arns" {
  type        = map(string)
  description = "Map of Lambda function name → ARN for lambda_ref task states"
  default     = {}
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "tags" {
  type    = map(string)
  default = {}
}
