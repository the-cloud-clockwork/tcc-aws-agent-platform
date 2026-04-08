variable "lambdas" {
  description = "Map of Lambda functions to create alarms for. Key is logical name, value has function_name and timeout."
  type = map(object({
    function_name = string
    timeout       = number
  }))
}

variable "alarm_actions" {
  description = "List of ARNs to notify when an alarm transitions to ALARM state."
  type        = list(string)
}

variable "resource_prefix" {
  description = "Prefix for alarm names."
  type        = string
}

variable "tags" {
  description = "Tags applied to all alarms."
  type        = map(string)
  default     = {}
}
