variable "name" {
  description = "Logical name for the schedule (used in resource names)."
  type        = string
}

variable "schedule_expression" {
  description = "EventBridge schedule expression (cron or rate)."
  type        = string
}

variable "description" {
  description = "Human-readable description of the schedule."
  type        = string
  default     = ""
}

variable "function_name" {
  description = "Lambda function name to invoke."
  type        = string
}

variable "function_arn" {
  description = "Lambda function ARN to invoke."
  type        = string
}

variable "resource_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default     = {}
}
