output "state_machine_arns" {
  description = "Map of workflow ID → State Machine ARN"
  value = {
    for k, sm in aws_sfn_state_machine.workflows :
    k => sm.arn
  }
}

output "state_machine_names" {
  description = "Map of workflow ID → State Machine name"
  value = {
    for k, sm in aws_sfn_state_machine.workflows :
    k => sm.name
  }
}

output "workflow_ids" {
  description = "List of all workflow IDs parsed from YAML"
  value       = keys(local.workflows)
}
