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

# Per-runtime authorizer visibility. Lets operators confirm MCP Runtimes have
# the inbound JWT authorizer attached after every apply. Drift (authorizer
# silently null because mcp_oauth2_discovery_url was empty at create time)
# is invisible on the AWS console unless you click into each Runtime, so
# exposing it here gives cheap `terraform output` checks and CI diffs.
output "mcp_runtime_authorizer_status" {
  description = "Per-Runtime authorizer state: protocol, whether a JWT authorizer is attached, and discovery URL if present."
  value = {
    for id, r in aws_bedrockagentcore_agent_runtime.agent : id => {
      protocol       = try(r.protocol_configuration[0].server_protocol, "HTTP")
      has_authorizer = length(r.authorizer_configuration) > 0
      discovery_url = try(
        r.authorizer_configuration[0].custom_jwt_authorizer[0].discovery_url,
        null,
      )
    }
  }
}
