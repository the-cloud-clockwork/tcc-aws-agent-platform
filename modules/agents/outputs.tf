# ──────────────────────────────────────────────────────────────────────────────
# Agents Module -- Outputs
# ──────────────────────────────────────────────────────────────────────────────

output "runtime_arns" {
  description = "Map of agent_id to AgentCore Runtime ARN."
  value = {
    for agent_id, runtime in aws_bedrockagentcore_agent_runtime.agent :
    agent_id => runtime.agent_runtime_arn
  }
}

output "runtime_names" {
  description = "Map of agent_id to AgentCore Runtime name."
  value = {
    for agent_id, runtime in aws_bedrockagentcore_agent_runtime.agent :
    agent_id => runtime.agent_runtime_name
  }
}

output "ecr_repository_urls" {
  description = "Map of agent_id to ECR repository URL."
  value = {
    for agent_id, repo in aws_ecr_repository.agent :
    agent_id => repo.repository_url
  }
}

output "agent_ids" {
  description = "List of all agent IDs parsed from blueprint YAML files."
  value       = keys(local.blueprints)
}

output "runtime_endpoint_urls" {
  description = "Map of agent_id to Runtime Endpoint URL."
  value = {
    for id, ep in aws_bedrockagentcore_agent_runtime_endpoint.agent :
    id => try(ep.endpoint_url, ep.agent_runtime_endpoint_arn)
  }
}

output "observe_script_path" {
  description = "Path to the observe-runtime.sh script shipped with this module."
  value       = "${path.module}/scripts/observe-runtime.sh"
}
