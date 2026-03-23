# ──────────────────────────────────────────────────────────────────────────────
# Agents Module -- Locals
#
# Parses blueprint YAML files and derives per-agent configuration maps
# consumed by all other resource files in this module.
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # Read all YAML files from blueprint directory
  blueprint_files = fileset(var.blueprint_dir, "*.yaml")

  # Decode each blueprint into a map keyed by agent ID
  blueprints = {
    for f in local.blueprint_files :
    yamldecode(file("${var.blueprint_dir}/${f}")).id => yamldecode(file("${var.blueprint_dir}/${f}"))
  }

  # Read gateway targets file if provided
  gateway_targets = var.gateway_targets_file != "" ? yamldecode(file(var.gateway_targets_file)) : { targets = [] }

  # Flatten memory strategies across all agents
  agent_memory_strategies = flatten([
    for agent_id, bp in local.blueprints : [
      for strategy in try(bp.memory.strategies, []) : {
        key       = "${agent_id}-${strategy.name}"
        agent_id  = agent_id
        type      = upper(strategy.type)
        name      = strategy.name
        namespace = try(strategy.namespace, "")
      }
    ]
  ])

  # Flatten identity credentials across all agents -- API key type
  agent_api_key_credentials = flatten([
    for agent_id, bp in local.blueprints : [
      for cred in try(bp.identity.credentials, []) : {
        key      = "${agent_id}-${cred.name}"
        agent_id = agent_id
        name     = cred.name
        provider = cred.provider
      }
      if try(cred.type, "") == "api_key"
    ]
  ])

  # Flatten identity credentials across all agents -- OAuth types
  agent_oauth_credentials = flatten([
    for agent_id, bp in local.blueprints : [
      for cred in try(bp.identity.credentials, []) : {
        key                    = "${agent_id}-${cred.name}"
        agent_id               = agent_id
        name                   = cred.name
        provider               = try(cred.provider, cred.name)
        scopes                 = try(cred.scopes, [])
        auth_flow              = try(cred.auth_flow, "M2M")
        discovery_url          = try(cred.discovery_url, "")
        client_id_ssm_path     = try(cred.client_id_ssm_path, "${var.ssm_root_path}/agents/${agent_id}/oauth/${cred.name}/client-id")
        client_secret_ssm_path = try(cred.client_secret_ssm_path, "${var.ssm_root_path}/agents/${agent_id}/oauth/${cred.name}/client-secret")
      }
      if contains(["oauth_3lo", "oauth2", "m2m"], try(cred.type, ""))
    ]
  ])

  name_prefix = "${var.resource_prefix}-${var.environment}"

  tags = merge(var.tags, {
    Module = "agents"
  })
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
